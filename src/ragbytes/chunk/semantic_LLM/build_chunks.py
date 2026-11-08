"""Build chunk text by slicing the original sentences."""

from dataclasses import dataclass

from ragbytes.chunk.assemble import (
    _content,
    _embed_text as _section_embed_text,
    _offset_text,
    titled_path,
)
from ragbytes.chunk.semantic_LLM.text_prep import FigureUnit, ProseRun, TaggedSentence
from ragbytes.schemas import Chunk, ChunkDetails, ChunkMetadata, Section, SectionKind


@dataclass
class BuiltChunk:
    """One topic cut from the original sentences.

    ``title`` is the short name from the model. ``text`` is the sentences
    from ``start`` up to the next start, joined by a space.
    """

    title: str
    text: str
    start: int


def build_chunks(sentences: list[str], splits: list[tuple[int, str]]) -> list[BuiltChunk]:
    """Join the original sentences between the checked starts.

    ``splits`` is the checked list as pairs of ``(start, title)``. Those
    starts are in order, unique, and inside the list, and the first is 0,
    so each slice runs forward and holds at least one sentence.
    """
    if not sentences:
        return []
    starts = [start for start, _title in splits] or [0]
    titles = {start: title for start, title in splits}
    bounds = [*starts, len(sentences)]
    chunks: list[BuiltChunk] = []
    for begin, end in zip(bounds, bounds[1:]):
        chunks.append(
            BuiltChunk(
                title=titles.get(begin, ""),
                text=" ".join(sentences[begin:end]),
                start=begin,
            )
        )
        return chunks


def build_chunk_records(
    sentences: list[TaggedSentence],
    splits: list[tuple[int, str]],
    *,
    filename: str,
) -> list[Chunk]:
    """Turn checked cuts into the same chunk records the other tiers return.

    ``splits`` are ``(start, topic)`` pairs. ``content`` is the original
    sentences joined by a space. The topic is metadata, so it is not written
    into that text. A slice that stays on one heading path uses the same
    embed text as the other tiers. A slice that crosses paths writes each
    path once, above the sentences that came from it.
    """
    records, _cursor = _prose_records(
        sentences,
        splits,
        filename=filename,
        cursor=0,
        chunk_number=0,
        leading_gap=False,
    )
    return records


def assemble_llm_chunks(
    units: list[ProseRun | FigureUnit],
    prose_splits: list[list[tuple[int, str]]],
    figure_topics: list[str],
    *,
    filename: str,
) -> list[Chunk]:
    """Join prose cuts and figure chunks in file order.

    ``prose_splits`` has one checked split list per prose run, in the same
    order as those runs. ``figure_topics`` has one title per figure. A blank
    title is stored as null. Chunk numbers and text offsets continue across
    both kinds. A figure's bytes use its label for the offset, and its title
    stays in metadata.
    """
    records: list[Chunk] = []
    cursor = 0
    prose_index = 0
    figure_index = 0
    for unit in units:
        leading = bool(records)
        if isinstance(unit, ProseRun):
            part, cursor = _prose_records(
                unit.sentences,
                prose_splits[prose_index],
                filename=filename,
                cursor=cursor,
                chunk_number=len(records),
                leading_gap=leading,
            )
            prose_index += 1
            records.extend(part)
            continue
        chunk, cursor = _figure_record(
            unit.section,
            figure_topics[figure_index],
            filename=filename,
            cursor=cursor,
            chunk_number=len(records),
            leading_gap=leading,
        )
        figure_index += 1
        records.append(chunk)
    return records


def _prose_records(
    sentences: list[TaggedSentence],
    splits: list[tuple[int, str]],
    *,
    filename: str,
    cursor: int,
    chunk_number: int,
    leading_gap: bool,
) -> tuple[list[Chunk], int]:
    if not sentences:
        return [], cursor
    chosen = _usable_splits(len(sentences), splits)
    bounds = [start for start, _topic in chosen]
    bounds.append(len(sentences))
    topics = {start: topic for start, topic in chosen}
    records: list[Chunk] = []
    for begin, end in zip(bounds, bounds[1:]):
        part = sentences[begin:end]
        if not part:
            continue
        content = " ".join(sentence.text for sentence in part)
        if records or leading_gap:
            cursor += 2
        start = cursor
        cursor += len(content)
        first = part[0]
        paths = _paths(part)
        pages = _pages(part)
        records.append(
            Chunk(
                content=content,
                embed_text=_embed_text(part),
                metadata=ChunkMetadata(
                    filename=filename,
                    file_id=first.file_id,
                    chunk_number=chunk_number + len(records),
                    title=first.title,
                    topic=_topic(topics.get(begin, "")),
                    headings=list(first.headings),
                    heading=first.heading,
                    subheading=first.subheading,
                    heading_paths=paths,
                    page=pages[0] if pages else None,
                    pages=pages,
                    format=_format(part),
                    details=ChunkDetails(start=start, end=cursor),
                ),
            )
        )
    return records, cursor


def _figure_record(
    section: Section,
    topic: str,
    *,
    filename: str,
    cursor: int,
    chunk_number: int,
    leading_gap: bool,
) -> tuple[Chunk, int]:
    content = _content(section)
    placed = _offset_text(section, content)
    if leading_gap:
        cursor += 2
    start = cursor
    cursor += len(placed)
    return (
        Chunk(
            content=content,
            embed_text=_section_embed_text(section),
            metadata=ChunkMetadata(
                filename=filename,
                file_id=section.file_id,
                chunk_number=chunk_number,
                title=section.title,
                topic=_topic(topic),
                headings=list(section.headings),
                heading=section.heading,
                subheading=section.subheading,
                heading_paths=[list(section.headings)] if section.headings else [],
                page=section.page,
                pages=[section.page] if section.page is not None else [],
                format=section.kind,
                media_type=section.media_type if section.media else None,
                details=ChunkDetails(start=start, end=cursor),
            ),
        ),
        cursor,
    )


def _usable_splits(count: int, splits: list[tuple[int, str]]) -> list[tuple[int, str]]:
    chosen: list[tuple[int, str]] = []
    seen: set[int] = set()
    for start, topic in splits:
        if type(start) is not int or start in seen or not 0 <= start < count:
            continue
        seen.add(start)
        chosen.append((start, topic))
    if 0 not in seen:
        chosen.insert(0, (0, ""))
    chosen.sort(key=lambda item: item[0])
    return chosen


def _topic(topic: str) -> str | None:
    stripped = topic.strip()
    return stripped or None


def _paths(part: list[TaggedSentence]) -> list[list[str]]:
    paths: list[list[str]] = []
    for sentence in part:
        path = list(sentence.headings)
        if path and path not in paths:
            paths.append(path)
    return paths


def _pages(part: list[TaggedSentence]) -> list[int]:
    pages: list[int] = []
    for sentence in part:
        if sentence.page is not None and sentence.page not in pages:
            pages.append(sentence.page)
    return pages


def _format(part: list[TaggedSentence]) -> SectionKind:
    kinds = {sentence.kind for sentence in part}
    if len(kinds) == 1:
        return part[0].kind
    return "text"


def _embed_text(part: list[TaggedSentence]) -> str:
    groups = _groups(part)
    title = part[0].title
    if len(groups) == 1:
        path, text = groups[0]
        joined = " > ".join(titled_path(title, path))
        if not joined:
            return text
        return f"{joined}\n\n{text}"
    blocks: list[str] = []
    if title:
        blocks.append(title)
    for path, text in groups:
        if path:
            blocks.append(" > ".join(path))
        blocks.append(text)
    return "\n\n".join(blocks)


def _groups(part: list[TaggedSentence]) -> list[tuple[list[str], str]]:
    groups: list[tuple[list[str], list[str]]] = []
    for sentence in part:
        if groups and groups[-1][0] == sentence.headings:
            groups[-1][1].append(sentence.text)
            continue
        groups.append((list(sentence.headings), [sentence.text]))
    return [(path, " ".join(texts)) for path, texts in groups]


if __name__ == "__main__":
    from ragbytes.chunk.semantic_LLM.text_prep import number_sentences

    sample = (
        "The company was founded in 2012. "
        "It sells accounting software to small firms. "
        "Revenue grew 40% last year.\n\n"
        "The office dog is named Biscuit. "
        "Biscuit comes to work on Fridays."
    )
    prepared = number_sentences(sample)
    chunks = build_chunks(
        prepared.sentences,
        [(0, "Company overview"), (3, "Office dog")],
    )
    for chunk in chunks:
        print(chunk.start, chunk.title)
        print(chunk.text)
        print("---")