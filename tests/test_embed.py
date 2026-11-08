import io
import json
from urllib import error

import pytest

from ragbytes.chunk.semantic_embed import embed
from ragbytes.chunk.semantic_embed.embed import MAX_INPUT_CHARS, OpenAIEmbedder, embed_texts


class _Response(io.BytesIO):
    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _reply(texts: list[str]) -> _Response:
    rows = [{"index": index, "embedding": [float(len(text))]} for index, text in enumerate(texts)]
    return _Response(json.dumps({"data": rows}).encode())


def _http_error(code: int) -> error.HTTPError:
    return error.HTTPError(embed.EMBEDDING_URL, code, "error", {}, io.BytesIO(b"{}"))


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    sent: list[list[str]] = []

    def urlopen(call, timeout):
        texts = json.loads(call.data)["input"]
        sent.append(texts)
        return _reply(texts)

    monkeypatch.setattr(embed.request, "urlopen", urlopen)
    monkeypatch.setattr(embed.time, "sleep", lambda seconds: None)
    return sent


def test_a_very_long_passage_is_embedded_from_its_start():
    class _Capture:
        def __init__(self) -> None:
            self.texts: list[str] = []

        def embed(self, texts: list[str]) -> list[list[float]]:
            self.texts = texts
            return [[1.0] for _ in texts]

    capture = _Capture()
    embed_texts(["short", "x" * (MAX_INPUT_CHARS * 2)], capture)

    assert capture.texts == ["short", "x" * MAX_INPUT_CHARS]


def test_batches_stay_inside_the_request_size(calls, monkeypatch):
    monkeypatch.setattr(embed, "_BATCH_CHARS", 10)

    vectors = OpenAIEmbedder("key").embed(["aaaa", "bbbb", "cccc", "dd"])

    assert calls == [["aaaa", "bbbb"], ["cccc", "dd"]]
    assert vectors == [[4.0], [4.0], [4.0], [2.0]]


def test_a_rate_limit_is_retried(calls, monkeypatch):
    replies = [_http_error(429)]

    def urlopen(call, timeout):
        if replies:
            raise replies.pop()
        return _reply(json.loads(call.data)["input"])

    monkeypatch.setattr(embed.request, "urlopen", urlopen)

    assert OpenAIEmbedder("key").embed(["abc"]) == [[3.0]]


def test_a_rejected_request_is_not_retried(calls, monkeypatch):
    attempts: list[int] = []

    def urlopen(call, timeout):
        attempts.append(1)
        raise _http_error(400)

    monkeypatch.setattr(embed.request, "urlopen", urlopen)

    with pytest.raises(RuntimeError, match="400"):
        OpenAIEmbedder("key").embed(["abc"])
    assert len(attempts) == 1


def test_a_server_error_gives_up_after_a_few_attempts(calls, monkeypatch):
    attempts: list[int] = []

    def urlopen(call, timeout):
        attempts.append(1)
        raise _http_error(503)

    monkeypatch.setattr(embed.request, "urlopen", urlopen)

    with pytest.raises(RuntimeError, match="503"):
        OpenAIEmbedder("key").embed(["abc"])
    assert len(attempts) == embed._ATTEMPTS
