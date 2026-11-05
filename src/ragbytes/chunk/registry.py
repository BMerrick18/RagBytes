"""Look up a chunking tier by its public name."""

from collections.abc import Callable

from ragbytes.chunk.simple import chunk_simple
from ragbytes.chunk.structured import chunk_structured
from ragbytes.schemas import Chunk

Chunker = Callable[..., list[Chunk]]

# semantic and enriched register here once each method is written. Each tier is served at
# POST /v1/chunk/<name>.
CHUNKERS: dict[str, Chunker] = {
    "basic": chunk_simple,
    "structured": chunk_structured,
}

DESCRIPTIONS: dict[str, str] = {
    "basic": (
        "Cuts the document about every 500 characters, including across headings. A sentence that would "
        "pass that limit starts the next chunk. A sentence longer than 500 characters is split at the "
        "word boundary closest to 500. Images, charts, and complex regions stay whole."
    ),
    "structured": (
        "One chunk per heading and subheading, with no minimum length. A short subsection stays its own "
        "chunk, and a section is split only once it passes about 2,000 characters. When a paragraph is "
        "split, the next chunk repeats its last sentence."
    ),
}


def get_chunker(name: str) -> Chunker | None:
    """Return the chunker for a tier name, if one is registered."""
    return CHUNKERS.get(name)
