from ragbytes.schemas import Chunk, ChunkDetails, ChunkMetadata, Section

_TEXT_MEDIA_TYPES = frozenset({"application/xml", "application/xhtml+xml"})


def sections_for_chunking(sections: list[Section], *, filename: str, exact: bool = False) -> list[Chunk]:
    """Shape extracted sections into response records, in file order.

    This does not chunk. Each section becomes one record. ``content`` is the
    section text, or the original region when the section holds an image or a
    complex table. ``metadata.format`` says which. ``embed_text`` is the
    heading path followed by the section's text or label, so an embedding
    of a short row or a figure still carries where in the file it sits.
    ``chunk_number`` counts the records in file order, starting at 0.
    ``start`` and ``end`` are offsets into the text contents joined by a blank
    line. A chunk whose content is bytes keeps its place using the section's
    text label.
    """
    records: list[Chunk] = []
    cursor = 0
    for section in sorted(sections, key=lambda section: section.index):
        content = _content(section, exact=exact)
        placed = _offset_text(section, content, exact=exact)
        if not placed:
            continue
        if records:
            cursor += 2
        start = cursor
        end = start + len(placed)
        cursor = end
        records.append(
            Chunk(
                content=content,
                embed_text=_embed_text(section, exact=exact),
                metadata=ChunkMetadata(
                    filename=filename,
                    file_id=section.file_id,
                    chunk_number=len(records),
                    title=section.title,
                    headings=list(section.headings),
                    heading=section.heading,
                    subheading=section.subheading,
                    page=section.page,
                    format=section.kind,
                    media_type=section.media_type if section.media else None,
                    details=ChunkDetails(start=start, end=end),
                ),
            )
        )
    return records


def _content(section: Section, *, exact: bool = False) -> str | bytes:
    """Return the one value this section contributes."""
    if section.media and _media_is_text(section.media_type):
        return section.media.decode("utf-8")
    if section.media:
        return section.media
    return _plain(section, exact=exact)


def _media_is_text(media_type: str | None) -> bool:
    if not media_type:
        return False
    return media_type.startswith("text/") or media_type in _TEXT_MEDIA_TYPES


def _embed_text(section: Section, *, exact: bool = False) -> str:
    """Return the title and heading path, then the section's text or label, for embedding."""
    text = _plain(section, exact=exact)
    path = " > ".join(titled_path(section.title, section.headings))
    if not path:
        return text
    if exact and (text == path or text.startswith(f"{path}\n")):
        return text
    return f"{path}\n\n{text}"


def titled_path(title: str | None, headings: list[str]) -> list[str]:
    """The document title, when there is one, followed by the heading path."""
    return [title, *headings] if title else list(headings)


def _offset_text(section: Section, content: str | bytes, *, exact: bool = False) -> str:
    if isinstance(content, str):
        return content
    return _plain(section, exact=exact)


def _plain(section: Section, *, exact: bool) -> str:
    """Return the section text, keeping a character window's edge spaces when ``exact``."""
    if exact:
        return section.data
    return section.data.strip()
