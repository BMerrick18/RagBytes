"""Turn passage text into embedding vectors."""

import json
import time
from collections.abc import Sequence
from typing import Protocol
from urllib import error, request

EMBEDDING_URL = "https://api.openai.com/v1/embeddings"
DEFAULT_MODEL = "text-embedding-3-small"
_BATCH = 2048
# One input may hold 8,191 tokens, and a token is never shorter than one
# character, so this many characters always fits. The start of a very long
# table or code block is enough to compare it with its neighbours.
MAX_INPUT_CHARS = 8000
# One request may hold 300,000 tokens across all of its inputs.
_BATCH_CHARS = 300_000
_ATTEMPTS = 4
_RETRY_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})


class Embedder(Protocol):
    """Something that returns one vector per input string, in the same order."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector for each string in ``texts``."""


def embed_texts(texts: Sequence[str], embedder: Embedder) -> list[list[float]]:
    """Embed each string, preserving order.

    An empty list makes no request. The caller embeds passage bodies, not the
    heading path: inside one heading every path is the same, so the path would
    only pull the similarity scores together. A string longer than about 8,000
    characters is embedded from its start, so it never passes the input limit.
    """
    if not texts:
        return []
    vectors = embedder.embed([text[:MAX_INPUT_CHARS] for text in texts])
    if len(vectors) != len(texts):
        raise RuntimeError(f"Embedding returned {len(vectors)} vectors for {len(texts)} texts.")
    return vectors


class OpenAIEmbedder:
    """OpenAI embeddings over ``POST /v1/embeddings``.

    The API key belongs to the caller. It is sent on the request and is not
    stored. Inputs are sent in batches of up to 2048 strings and about 300,000
    characters, which stays inside the request limits, and the vectors come
    back in the same order as the texts. A rate limit, a timeout, or a server
    error is retried a few times with a growing pause.
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout: float = 60) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for batch in _batches(texts):
            vectors.extend(self._request(batch))
        return vectors

    def _request(self, texts: list[str]) -> list[list[float]]:
        for attempt in range(_ATTEMPTS):
            try:
                return self._send(texts)
            except error.HTTPError as exc:
                exc.read()
                if exc.code not in _RETRY_STATUSES or attempt + 1 == _ATTEMPTS:
                    raise RuntimeError(f"Embedding request failed ({exc.code}).") from exc
            except (error.URLError, TimeoutError):
                if attempt + 1 == _ATTEMPTS:
                    raise
            time.sleep(2**attempt)
        raise RuntimeError("Embedding request failed.")

    def _send(self, texts: list[str]) -> list[list[float]]:
        payload = json.dumps({"model": self.model, "input": texts}).encode()
        call = request.Request(
            EMBEDDING_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(call, timeout=self.timeout) as response:
            body = json.loads(response.read().decode())
        rows = body.get("data", [])
        ordered = sorted(rows, key=lambda row: row["index"])
        return [list(row["embedding"]) for row in ordered]


def _batches(texts: list[str]) -> list[list[str]]:
    """Group texts in order, each group inside the count and size limits."""
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for text in texts:
        if current and (len(current) == _BATCH or size + len(text) > _BATCH_CHARS):
            batches.append(current)
            current = []
            size = 0
        current.append(text)
        size += len(text)
    if current:
        batches.append(current)
    return batches
