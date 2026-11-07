import base64
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field, field_serializer

SectionKind = Literal["text", "list", "table", "image", "chart", "code", "complex"]
Complexity = Literal["simple", "complex"]


def _complexity(kind: SectionKind) -> Complexity:
    """Return whether a section can be chunked now."""
    if kind == "complex":
        return "complex"
    return "simple"


class Section(BaseModel):
    """One element from an uploaded file.

    ``data`` is the text of that element. An image also keeps its bytes in
    ``media``. Those bytes stay on the section. A complex section is a cell
    or figure the walk could not linearize. Its text is ``[Complex]`` and
    ``media`` holds that leftover region. ``index`` is the
    section's place in the file, starting at 0. ``file_id`` is stamped by
    the request after extraction.

    ``headings`` is the heading path, outer title first. The shallowest
    heading level in the file is level 1. ``heading`` is that outer title.
    ``subheading`` is the nearest deeper title. ``title`` is the document's
    title, such as the name at the top of a CV: a single outermost heading
    that every later heading sits under. It is not part of ``headings``.
    ``complexity`` is ``simple`` when the section can be chunked, and
    ``complex`` when it needs further processing first.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    file_id: str = ""
    index: int = 0
    kind: SectionKind
    title: str | None = None
    headings: list[str] = Field(default_factory=list)
    heading: str | None = None
    subheading: str | None = None
    page: int | None = None
    data: str = ""
    media: bytes | None = None
    media_type: str | None = None

    @computed_field
    @property
    def complexity(self) -> Complexity:
        """``simple`` can be chunked. ``complex`` needs further processing."""
        return _complexity(self.kind)


class SectionResponse(BaseModel):
    """Labeled sections from one upload, ready for a later chunking stage."""

    filename: str
    file_id: str
    sections: list[Section]


class ChunkDetails(BaseModel):
    """Where this chunk sits in the chunked document text."""

    start: int = Field(description="Start offset in the chunked document text.")
    end: int = Field(description="End offset in the chunked document text.")


class ChunkMetadata(BaseModel):
    filename: str
    file_id: str
    chunk_number: int = Field(description="Place of this chunk in the response, starting at 0.")
    title: str | None = Field(
        default=None,
        description="The document's title, such as the name at the top of a CV, when one heading sits above all the others.",
    )
    headings: list[str] = Field(default_factory=list)
    heading: str | None = None
    subheading: str | None = None
    page: int | None = None
    format: SectionKind
    media_type: str | None = None
    details: ChunkDetails


class Chunk(BaseModel):
    """One piece of a file.

    ``chunk_id`` identifies this chunk. A section split into several chunks
    gets a new id on each one. ``metadata`` is written before ``content``.
    ``embed_text`` is the string to embed: the document title and heading
    path, a blank line, then the chunk's text, or its label when the chunk is an image or a
    complex region. ``content`` is the one value for this chunk: the text, or
    the original bytes of an image or complex region. ``metadata.format``
    says which it is. Bytes are base64 in the response.
    """

    chunk_id: str = Field(default_factory=lambda: str(uuid4()))
    metadata: ChunkMetadata
    embed_text: str = Field(
        description="Heading path and chunk text, ready to embed. An image or complex region uses its label."
    )
    content: str | bytes

    @field_serializer("content", when_used="json")
    def _serialize_content(self, content: str | bytes) -> str:
        if isinstance(content, bytes):
            return base64.b64encode(content).decode("ascii")
        return content


class ChunkResponse(BaseModel):
    filename: str
    file_id: str
    chunks: list[Chunk]


class SemanticOptions(BaseModel):
    """The settings a semantic response was cut with, so the same result can be asked for again."""

    style: Literal["precise", "balanced", "broad"]
    strict_headings: bool
    max_chunk_chars: int = Field(description="The largest a chunk was allowed to grow, in characters.")


class SemanticChunkResponse(ChunkResponse):
    options: SemanticOptions


class ChunkingMethod(BaseModel):
    name: str = Field(description="Tier name.")
    path: str = Field(description="Endpoint to POST a file to for this tier.")
    description: str


class MethodsResponse(BaseModel):
    methods: list[ChunkingMethod]
    file_types: list[str] = Field(description="Filename suffixes that can be uploaded.")


class ErrorResponse(BaseModel):
    detail: str


class StatsResponse(BaseModel):
    documents: int = Field(description="Documents chunked since the service started counting.")
    chunks: int = Field(description="Chunks returned for those documents.")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str = Field(description="Commit SHA the running image was built from, or dev.")
