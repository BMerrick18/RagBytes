from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ragbytes import stats
from ragbytes.chunk.registry import CHUNKERS, DESCRIPTIONS, Chunker
from ragbytes.extract.complex import prepare_for_chunking
from ragbytes.extract.registry import EXTRACTORS, Extractor, get_extractor
from ragbytes.schemas import ChunkingMethod, ChunkResponse, ErrorResponse, MethodsResponse, StatsResponse

router = APIRouter()

class ChunkUpload(BaseModel):
    file: UploadFile = Field(
        description=f"The document to chunk. Its filename must end in one of: {', '.join(EXTRACTORS)}."
    )


Upload = Annotated[ChunkUpload, File()]

ERRORS: dict[int | str, dict] = {
    400: {"model": ErrorResponse, "description": "The file could not be read."},
    415: {"model": ErrorResponse, "description": "The filename suffix is not a supported file type."},
}


@router.get("/methods", tags=["service"])
def list_methods() -> MethodsResponse:
    """List the chunking tiers, the endpoint for each, and the file types this service accepts."""
    return MethodsResponse(
        methods=[
            ChunkingMethod(name=name, path=f"/v1/chunk/{name}", description=DESCRIPTIONS[name]) for name in CHUNKERS
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
