"""Look up a chunking tier by its public name."""

from collections.abc import Callable

from ragbytes.chunk.semantic.hosted import chunk_semantic_hosted
from ragbytes.chunk.simple import chunk_simple
from ragbytes.chunk.structured import chunk_structured
from ragbytes.schemas import Chunk

Chunker = Callable[..., list[Chunk]]

# enriched registers here once that method is written. Each tier is served at
# POST /v1/chunk/<name>.
CHUNKERS: dict[str, Chunker] = {
    "basic": chunk_simple,
    "structured": chunk_structured,
    "semantic": chunk_semantic_hosted,
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
    "semantic": (
        "Embeds neighbouring passages and starts a new chunk where the meaning shifts. A chunk stays "
        "inside one heading, except that very short neighbouring headings can share a chunk under "
        "their parent heading. Choose a style: precise for small focused chunks, balanced for general "
        "search, or broad for larger chunks with more context. strict_headings keeps every heading "
        "apart, and max_chunk_chars caps the chunk size. Passage text is sent to OpenAI for those "
        "embeddings and then discarded."
    ),
}


def get_chunker(name: str) -> Chunker | None:
    """Return the chunker for a tier name, if one is registered."""
    return CHUNKERS.get(name)
