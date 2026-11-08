from functools import partial
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ragbytes import stats
from ragbytes.chunk.registry import CHUNKERS, DESCRIPTIONS, Chunker
from ragbytes.chunk.semantic.hosted import SemanticEmbedError, SemanticNotConfigured
from ragbytes.chunk.semantic.styles import StyleName, resolve_style
from ragbytes.config import settings
from ragbytes.extract.complex import prepare_for_chunking
from ragbytes.extract.registry import EXTRACTORS, Extractor, get_extractor
from ragbytes.schemas import (
    ChunkingMethod,
    ChunkResponse,
    ErrorResponse,
    MethodsResponse,
    SemanticChunkResponse,
    SemanticOptions,
    StatsResponse,
)

router = APIRouter()

class ChunkUpload(BaseModel):
    file: UploadFile = Field(
        description=f"The document to chunk. Its filename must end in one of: {', '.join(EXTRACTORS)}."
    )


Upload = Annotated[ChunkUpload, File()]


class SemanticChunkUpload(ChunkUpload):
    style: StyleName = Field(
        default="balanced",
        description=(
            "precise makes small, tightly focused chunks for question answering. balanced suits general "
            "search. broad makes larger chunks that keep more context, for long-context models."
        ),
    )
    strict_headings: bool = Field(
        default=False,
        description="Never let a chunk span two headings, even when both are very short.",
    )
    max_chunk_chars: int | None = Field(
        default=None,
        ge=500,
        le=8000,
        description="The largest a chunk may grow, in characters. Defaults to the style's own limit.",
    )


SemanticUpload = Annotated[SemanticChunkUpload, File()]

ERRORS: dict[int | str, dict] = {
    400: {"model": ErrorResponse, "description": "The file could not be read."},
    415: {"model": ErrorResponse, "description": "The filename suffix is not a supported file type."},
}


def published_tiers() -> list[str]:
    """Tier names currently served. Semantic stays implemented and is omitted while switched off."""
    if settings.semantic_enabled:
        return list(CHUNKERS)
    return [name for name in CHUNKERS if name != "semantic"]


@router.get("/methods", tags=["service"])
def list_methods() -> MethodsResponse:
    """List the chunking tiers, the endpoint for each, and the file types this service accepts."""
    return MethodsResponse(
        methods=[
            ChunkingMethod(name=name, path=f"/v1/chunk/{name}", description=DESCRIPTIONS[name])
            for name in published_tiers()
        ],
        file_types=list(EXTRACTORS),
    )


@router.get("/stats", tags=["service"])
def usage_stats() -> StatsResponse:
    """Count the documents chunked and the chunks returned. No document content is kept."""
    return stats.totals()


@router.post(
    "/chunk/basic",
    tags=["chunking"],
    summary="Basic: fixed-size chunks",
    description=DESCRIPTIONS["basic"],
    responses=ERRORS,
)
async def chunk_basic(upload: Upload) -> ChunkResponse:
    return await _chunk(upload.file, CHUNKERS["basic"])


@router.post(
    "/chunk/structured",
    tags=["chunking"],
    summary="Structured: follows titles and sections",
    description=DESCRIPTIONS["structured"],
    responses=ERRORS,
)
async def chunk_structured(upload: Upload) -> ChunkResponse:
    return await _chunk(upload.file, CHUNKERS["structured"])


def semantic_routes() -> APIRouter:
    """The semantic endpoint, mounted only while that tier is published."""
    semantic = APIRouter()

    @semantic.post(
        "/chunk/semantic",
        tags=["chunking"],
        summary="Semantic: splits where the meaning changes",
        description=DESCRIPTIONS["semantic"],
        responses={
            **ERRORS,
            502: {"model": ErrorResponse, "description": "The document could not be embedded."},
            503: {"model": ErrorResponse, "description": "Semantic chunking is not configured."},
        },
    )
    async def chunk_semantic(upload: SemanticUpload) -> SemanticChunkResponse:
        if not settings.openai_api_key.get_secret_value().strip():
            raise HTTPException(status_code=503, detail="Semantic chunking is unavailable.")
        style = resolve_style(upload.style, strict_headings=upload.strict_headings, max_chars=upload.max_chunk_chars)
        try:
            response = await _chunk(upload.file, partial(CHUNKERS["semantic"], style=style))
        except SemanticNotConfigured as exc:
            raise HTTPException(status_code=503, detail="Semantic chunking is unavailable.") from exc
        except SemanticEmbedError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return SemanticChunkResponse(
            filename=response.filename,
            file_id=response.file_id,
            chunks=response.chunks,
            options=SemanticOptions(
                style=style.name,
                strict_headings=not style.merge_headings,
                max_chunk_chars=style.max_chars,
            ),
        )

    return semantic


async def _chunk(file: UploadFile, chunker: Chunker) -> ChunkResponse:
    """Extract an upload and return its chunks in file order."""
    suffix = Path(file.filename or "").suffix
    extractor = get_extractor(suffix)
    if extractor is None:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {suffix or 'unknown'}",
        )

    data = await file.read()
    filename = file.filename or ""
    try:
        response = await run_in_threadpool(_extract_and_chunk, data, extractor, chunker, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stats.record(len(response.chunks))
    return response


def _extract_and_chunk(data: bytes, extractor: Extractor, chunker: Chunker, filename: str) -> ChunkResponse:
    """The CPU-bound part of a request, run off the event loop so other requests are still served."""
    file_id = str(uuid4())
    sections = prepare_for_chunking(extractor(data))
    for section in sections:
        section.file_id = file_id
    chunks = chunker(sections, filename=filename)
    if not chunks and any(section.kind == "complex" for section in sections):
        raise ValueError("No readable text was found. The file may be a scanned image.")
    return ChunkResponse(filename=filename, file_id=file_id, chunks=chunks)
