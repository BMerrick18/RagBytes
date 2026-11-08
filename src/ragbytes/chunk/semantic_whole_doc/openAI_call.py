"""Send an uploaded file to a model and read the chunk fields it returns."""

import base64
import json
from dataclasses import dataclass
from pathlib import Path

from ragbytes.chunk.semantic_LLM.openAI_call import DEFAULT_MODEL, _require_client

# One reply writes about this many characters, then a later reply continues.
_REPLY_CHARS = 12_000

_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".html": "text/html",
    ".htm": "text/html",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}

_INSTRUCTIONS = f"""\
You split one uploaded file into chunks by topic.

The user message contains the file itself. Read that file.
Return the chunks in file order.
content is the wording of that chunk, copied from the file.
Do not summarise, paraphrase, or leave wording out.
Do not repeat wording that belongs to another chunk.
A new subject starts a new chunk.
Keep the items of one list in the same chunk when they are one subject.
Keep a block of code in one chunk.
A table keeps its text in content, with format table.
An image, chart, or complex figure is its own chunk. Say what it shows in content.

In this reply, write at most {_REPLY_CHARS} characters of content in total.
If the file continues after the last chunk, set more to true.
If this reply reaches the end of the file, set more to false.

title is the document title, or an empty string when there is none.
topic is a short name for this chunk.
headings is the heading path, outer heading first. Use an empty list when there is none.
heading is the outer heading, or an empty string.
subheading is the nearest deeper heading, or an empty string.
heading_paths lists each heading path this chunk covers, outer heading first. List each path once.
page is the first page this chunk covers, or null when the file has no pages.
pages lists each page this chunk covers, in order. List each page once.
format is text, list, table, image, chart, code, or complex.
"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "more": {"type": "boolean"},
        "chunks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "topic": {"type": "string"},
                    "title": {"type": "string"},
                    "headings": {"type": "array", "items": {"type": "string"}},
                    "heading": {"type": "string"},
                    "subheading": {"type": "string"},
                    "heading_paths": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                    "page": {"type": ["integer", "null"]},
                    "pages": {"type": "array", "items": {"type": "integer"}},
                    "format": {
                        "type": "string",
                        "enum": ["text", "list", "table", "image", "chart", "code", "complex"],
                    },
                },
                "required": [
                    "content",
                    "topic",
                    "title",
                    "headings",
                    "heading",
                    "subheading",
                    "heading_paths",
                    "page",
                    "pages",
                    "format",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["more", "chunks"],
    "additionalProperties": False,
}


@dataclass
class ModelChunk:
    """The chunk fields the model returns. Blank strings are filled in later."""

    content: str
    topic: str
    title: str
    headings: list[str]
    heading: str
    subheading: str
    heading_paths: list[list[str]]
    page: int | None
    pages: list[int]
    format: str


@dataclass
class ModelReply:
    """One reply. ``more`` means the file continues after these chunks."""

    chunks: list[ModelChunk]
    more: bool


def file_message(data: bytes, filename: str, *, after: str | None = None) -> list[dict]:
    """The user message: the upload itself, and where to continue when asked.

    The bytes are attached unchanged. Nothing is read out of the file first.
    """
    name = filename or "upload"
    mime = _MIME.get(Path(name).suffix.lower(), "application/octet-stream")
    encoded = base64.b64encode(data).decode("ascii")
    parts: list[dict] = [
        {
            "type": "input_file",
            "filename": name,
            "file_data": f"data:{mime};base64,{encoded}",
        }
    ]
    if after:
        parts.append(
            {
                "type": "input_text",
                "text": (
                    "The file is attached again in full. "
                    "Continue with the next chunks after the chunk below. Do not repeat it.\n\n"
                    + after
                ),
            }
        )
    else:
        parts.append({"type": "input_text", "text": "The file is attached in full. Chunk it."})
    return parts


def ask_for_chunks(
    data: bytes,
    *,
    filename: str,
    after: str | None = None,
    model: str = DEFAULT_MODEL,
) -> ModelReply:
    """Send the upload and return the chunk fields from one reply.

    An empty upload makes no request. The call reads ``OPENAI_API_KEY`` from
    the environment, loading ``.env`` on first use. The file is not stored.
    A refusal or an empty reply raises ``RuntimeError``.
    """
    if not data:
        return ModelReply(chunks=[], more=False)
    response = _require_client().responses.create(
        model=model,
        temperature=0,
        store=False,
        max_output_tokens=16_384,
        instructions=_INSTRUCTIONS,
        input=[{"role": "user", "content": file_message(data, filename, after=after)}],
        text={
            "format": {
                "type": "json_schema",
                "name": "document_chunks",
                "strict": True,
                "schema": _SCHEMA,
            }
        },
    )
    return read_model_reply(_reply_text(response))


def read_model_reply(content: str | None, refusal: str | None = None) -> ModelReply:
    """Return the chunk fields from a reply.

    A refusal, an empty reply, or a reply that is not the expected JSON
    raises ``RuntimeError``. A chunk with no content is left out.
    """
    if refusal:
        raise RuntimeError("The model refused to chunk the document.")
    if not content or not content.strip():
        raise RuntimeError("The model returned no chunks.")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The model reply was cut off before the chunks were complete.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("The model returned no chunks.")
    chunks = parsed.get("chunks")
    if not isinstance(chunks, list):
        raise RuntimeError("The model returned no chunks.")
    written: list[ModelChunk] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        text = chunk.get("content")
        if not isinstance(text, str) or not text.strip():
            continue
        written.append(
            ModelChunk(
                content=text.strip(),
                topic=_text(chunk.get("topic")),
                title=_text(chunk.get("title")),
                headings=_strings(chunk.get("headings")),
                heading=_text(chunk.get("heading")),
                subheading=_text(chunk.get("subheading")),
                heading_paths=_paths(chunk.get("heading_paths")),
                page=_page(chunk.get("page")),
                pages=_pages(chunk.get("pages")),
                format=_text(chunk.get("format")),
            )
        )
    return ModelReply(chunks=written, more=parsed.get("more") is True)


def _reply_text(response) -> str:
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "message":
            continue
        for block in getattr(item, "content", []) or []:
            if getattr(block, "type", None) == "refusal":
                raise RuntimeError("The model refused to chunk the document.")
    return response.output_text


def _text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _paths(value: object) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    paths: list[list[str]] = []
    for item in value:
        path = _strings(item)
        if path and path not in paths:
            paths.append(path)
    return paths


def _pages(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    pages: list[int] = []
    for item in value:
        if type(item) is int and item not in pages:
            pages.append(item)
    return pages


def _page(value: object) -> int | None:
    if type(value) is int:
        return value
    return None
