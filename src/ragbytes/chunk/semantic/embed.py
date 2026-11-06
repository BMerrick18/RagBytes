"""Turn passage text into embedding vectors."""

import json
from collections.abc import Sequence
from typing import Protocol
from urllib import error, request

EMBEDDING_URL = "https://api.openai.com/v1/embeddings"
DEFAULT_MODEL = "text-embedding-3-small"
_BATCH = 2048


class Embedder(Protocol):
    """Something that returns one vector per input string, in the same order."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector for each string in ``texts``."""


def embed_texts(texts: Sequence[str], embedder: Embedder) -> list[list[float]]:
    """Embed each string, preserving order.

    An empty list makes no request. The caller embeds passage bodies, not the
    heading path: inside one heading every path is the same, so the path would
    only pull the similarity scores together.
    """
    if not texts:
        return []
    vectors = embedder.embed(list(texts))
    if len(vectors) != len(texts):
        raise RuntimeError(f"Embedding returned {len(vectors)} vectors for {len(texts)} texts.")
    return vectors


class OpenAIEmbedder:
    """OpenAI embeddings over ``POST /v1/embeddings``.

    The API key belongs to the caller. It is sent on the request and is not
    stored. Inputs are sent in batches of 2048, which is the request limit,
    and the vectors come back in the same order as the texts.
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout: float = 60) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            vectors.extend(self._request(texts[start : start + _BATCH]))
        return vectors

    def _request(self, texts: list[str]) -> list[list[float]]:
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
        try:
            with request.urlopen(call, timeout=self.timeout) as response:
                body = json.loads(response.read().decode())
        except error.HTTPError as exc:
            exc.read()
            raise RuntimeError(f"Embedding request failed ({exc.code}).") from exc
        rows = body.get("data", [])
        ordered = sorted(rows, key=lambda row: row["index"])
        return [list(row["embedding"]) for row in ordered]
