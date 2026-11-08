"""Cut an upload by sending the file itself to a model."""

from typing import cast

from ragbytes.chunk.assemble import titled_path
from ragbytes.chunk.semantic_whole_doc.openAI_call import ModelChunk, ModelReply, ask_for_chunks
from ragbytes.schemas import Chunk, ChunkDetails, ChunkMetadata, SectionKind

# A long file needs several replies. Each reply still receives the whole upload.
_MAX_ROUNDS = 40

_FORMATS = frozenset({"text", "list", "table", "image", "chart", "code", "complex"})


def chunk_whole_doc(data: bytes, *, filename: str, file_id: str = "") -> list[Chunk]:
    """Send the upload to the model and return the shared chunk records.

    The file bytes are attached as they were uploaded. This does not extract
    sections, sentences, or headings first. The model returns each chunk's
    wording and the chunk fields. A file that does not fit in one reply is
    sent again in full, and the model continues after the last chunk it wrote.
    ``chunk_number``, ``embed_text``, and the text offsets are filled in here
    so they match the other tiers. The calls store nothing.
    """
    if not data:
        return []
    written: list[ModelChunk] = []
    after: str | None = None
    for _round in range(_MAX_ROUNDS):
        reply = ask_for_chunks(data, filename=filename, after=after)
        fresh = _without_repeat(reply, after)
        if not fresh:
            break
        written.extend(fresh)
        if not reply.more:
            break
        after = fresh[-1].content
    else:
        raise RuntimeError("The document was longer than the replies could cover.")
    return records_from_chunks(written, filename=filename, file_id=file_id)


def records_from_chunks(
    chunks: list[ModelChunk],
    *,
    filename: str,
    file_id: str,
) -> list[Chunk]:
    """Turn the model's chunk fields into the records the other tiers return."""
    records: list[Chunk] = []
    cursor = 0
    for chunk in chunks:
        content = chunk.content.strip()
        if not content:
            continue
        if records:
            cursor += 2
        start = cursor
        cursor += len(content)
        headings = list(chunk.headings)
        heading = chunk.heading or (headings[0] if headings else None)
        subheading = chunk.subheading or (headings[-1] if len(headings) > 1 else None)
        paths = list(chunk.heading_paths) or ([headings] if headings else [])
        pages = list(chunk.pages)
        page = chunk.page if chunk.page is not None else (pages[0] if pages else None)
        if page is not None and page not in pages:
            pages.insert(0, page)
        records.append(
            Chunk(
                content=content,
                embed_text=_embed_text(chunk.title or None, paths, content),
                metadata=ChunkMetadata(
                    filename=filename,
                    file_id=file_id,
                    chunk_number=len(records),
                    title=chunk.title or None,
                    topic=chunk.topic or None,
                    headings=headings,
                    heading=heading,
                    subheading=subheading,
                    heading_paths=paths,
                    page=page,
                    pages=pages,
                    format=_format(chunk.format),
                    details=ChunkDetails(start=start, end=cursor),
                ),
            )
        )
    return records


def _without_repeat(reply: ModelReply, after: str | None) -> list[ModelChunk]:
    chunks = list(reply.chunks)
    if after and chunks and chunks[0].content.strip() == after.strip():
        return chunks[1:]
    return chunks


def _format(value: str) -> SectionKind:
    if value in _FORMATS:
        return cast(SectionKind, value)
    return "text"


def _embed_text(title: str | None, paths: list[list[str]], content: str) -> str:
    """The document title and heading path, a blank line, then the chunk text."""
    if len(paths) == 1:
        joined = " > ".join(titled_path(title, paths[0]))
        if not joined:
            return content
        return f"{joined}\n\n{content}"
    blocks: list[str] = []
    if title:
        blocks.append(title)
    for path in paths:
        if path:
            blocks.append(" > ".join(path))
    blocks.append(content)
    return "\n\n".join(blocks)
