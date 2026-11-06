"""Run semantic chunking with the server's OpenAI key."""

from ragbytes.chunk.semantic.embed import OpenAIEmbedder
from ragbytes.chunk.semantic.semantic import chunk_semantic
from ragbytes.config import settings
from ragbytes.schemas import Chunk, Section


class SemanticNotConfigured(Exception):
    """Semantic chunking has no key configured on the server."""


class SemanticEmbedError(Exception):
    """The embedding call failed. The message does not include the key or the document."""


def chunk_semantic_hosted(sections: list[Section], *, filename: str) -> list[Chunk]:
    """Chunk with the server's key. The request itself never carries a key.

    Passage text is sent to OpenAI and dropped with the rest of the upload when
    the response is returned. A missing key refuses the tier. A failed call
    reports that the document could not be embedded, and nothing else.
    """
    key = settings.openai_api_key.get_secret_value().strip()
    if not key:
        raise SemanticNotConfigured("Semantic chunking is unavailable.")
    try:
        return chunk_semantic(sections, filename=filename, embedder=OpenAIEmbedder(key))
    except (RuntimeError, OSError) as exc:
        raise SemanticEmbedError("The document could not be embedded.") from exc
