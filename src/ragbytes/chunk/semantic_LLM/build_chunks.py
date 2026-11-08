"""Build chunk text by slicing the original sentences."""

from dataclasses import dataclass

from ragbytes.chunk.assemble import titled_path
from ragbytes.chunk.semantic_LLM.text_prep import TaggedSentence
from ragbytes.schemas import Chunk, ChunkDetails, ChunkMetadata, SectionKind


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
    if not sentences:
        return []
    chosen = _usable_splits(len(sentences), splits)
    bounds = [start for start, _topic in chosen]
    bounds.append(len(sentences))
    topics = {start: topic for start, topic in chosen}
    records: list[Chunk] = []
    cursor = 0
    for begin, end in zip(bounds, bounds[1:]):
        part = sentences[begin:end]
        if not part:
            continue
        content = " ".join(sentence.text for sentence in part)
        if records:
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
                    chunk_number=len(records),
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
    return records


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