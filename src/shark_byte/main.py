from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shark_byte.api.routes import router
from shark_byte.config import settings
from shark_byte.schemas import HealthResponse

DESCRIPTION = """
Turn PDFs, Word documents, web pages, Markdown and plain text into chunks that are ready to embed.

Each chunking tier has its own endpoint: upload a file as `multipart/form-data` to
`POST /v1/chunk/basic` or `POST /v1/chunk/structured`. Each chunk comes back with `embed_text` (its
heading path, a blank line, then its text) to send to your embedding model, `content` to store
alongside the vector, and `metadata` describing where it came from.

Uploads are processed in memory and discarded once the response is sent. The service only keeps a
running count of documents chunked and chunks returned. Requests are limited to 50 MB, about 100
seconds, and a few per second from one address.
"""

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=DESCRIPTION,
    openapi_tags=[
        {"name": "chunking", "description": "Split a document into chunks. One endpoint per tier."},
        {"name": "service", "description": "Check the service is running and how much it has chunked."},
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/v1")


@app.get("/health", tags=["service"])
def health() -> HealthResponse:
    """Report that the service is up and which build it is running."""
    return HealthResponse(version=settings.version)
