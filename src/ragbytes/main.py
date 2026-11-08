from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ragbytes.api.routes import llm_routes, router, semantic_routes
from ragbytes.config import settings
from ragbytes.schemas import HealthResponse


def api_description() -> str:
    """Public API text. Semantic is mentioned only while that tier is published."""
    endpoints = ["`POST /v1/chunk/basic`", "`POST /v1/chunk/structured`"]
    if settings.semantic_enabled:
        endpoints.append("`POST /v1/chunk/semantic`")
    if settings.llm_enabled:
        endpoints.append("`POST /v1/chunk/llm`")
    if len(endpoints) == 2:
        listed = f"{endpoints[0]} or {endpoints[1]}"
    else:
        listed = ", ".join(endpoints[:-1]) + f", or {endpoints[-1]}"
    notes = ["The upload is a file only."]
    if settings.semantic_enabled:
        notes.insert(0, "Semantic sends passage text to OpenAI to find the cuts, then discards it with the file.")
    if settings.llm_enabled:
        notes.insert(
            0,
            "LLM chunking sends the uploaded file to OpenAI and asks for written topic chunks, then discards the file.",
        )
    return f"""
Turn PDFs, Word documents, web pages, Markdown and plain text into chunks that are ready to embed.

Each chunking tier has its own endpoint: upload a file as `multipart/form-data` to
{listed}. Each chunk comes
back with `embed_text` (its heading path, a blank line, then its text) to send to your embedding
model, `content` to store alongside the vector, and `metadata` describing where it came from.
{" ".join(notes)}

Uploads are processed in memory and discarded once the response is sent. The service only keeps a
running count of documents chunked and chunks returned. Requests are limited to 50 MB, about 100
seconds, and a few per second from one address.
"""


def create_app() -> FastAPI:
    """Build the API. Semantic and LLM are mounted only while their flags are set."""
    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=api_description(),
        openapi_tags=[
            {"name": "chunking", "description": "Split a document into chunks. One endpoint per tier."},
            {"name": "service", "description": "Check the service is running and how much it has chunked."},
        ],
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    application.include_router(router, prefix="/v1")
    if settings.semantic_enabled:
        application.include_router(semantic_routes(), prefix="/v1")
    if settings.llm_enabled:
        application.include_router(llm_routes(), prefix="/v1")

    @application.get("/health", tags=["service"])
    def health() -> HealthResponse:
        """Report that the service is up and which build it is running."""
        return HealthResponse(version=settings.version)

    return application


app = create_app()
