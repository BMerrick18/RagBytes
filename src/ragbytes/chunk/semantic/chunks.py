"""Turn cut indexes into sections, then into chunk records."""

from ragbytes.chunk.assemble import sections_for_chunking, titled_path
from ragbytes.chunk.semantic.embed_prep import HeadingPassages, PreparedSentence, _LIST_ITEM, _embed_text
from ragbytes.chunk.semantic.siblings import Umbrella
from ragbytes.schemas import Chunk, Section, SectionKind

_MEDIA_KINDS = frozenset({"image", "chart", "complex"})


def whole_after_first_pass(
    scope: HeadingPassages, cuts: dict[int, list[int]] | None = None
) -> list[PreparedSentence]:
    """Return the second-pass passages for one heading, in file order.

    ``cuts`` maps a group in ``to_embed`` to the indexes inside that group
    where a new section starts. The first sentence is always a start, and a
    group with no cuts becomes one section. Each section keeps the heading of
    its sentences and the order of its first sentence, so it sits in ``whole``
    where the long block was.
    """
    chosen = cuts or {}
    assembled: list[PreparedSentence] = []
    for group_id, sentences in _by_group(scope.to_embed):
        assembled.extend(_assemble_group(sentences, chosen.get(group_id, [])))
    return sorted([*scope.whole, *assembled], key=lambda passage: passage.order)


def chunk_sections(
    passages: list[PreparedSentence],
    cuts: list[int],
    originals: dict[str, Section],
    *,
    start_index: int,
    umbrella: Umbrella | None = None,
) -> list[Section]:
    """Join passages between ``cuts`` into sections the response can carry.

    ``cuts`` are indexes in ``passages`` where a new chunk starts. A run that
    is one image, chart, or complex region keeps that region's bytes. A run of
    several passages joins their text with a blank line. A run whose passages
    come from more than one heading takes the ``umbrella`` path they share,
    and each heading's own titles below that path are written on the line
    above its first passage.
    """
    if not passages:
        return []
    starts = sorted({0, *(cut for cut in cuts if 0 < cut < len(passages))})
    starts.append(len(passages))
    sections: list[Section] = []
    for begin, end in zip(starts, starts[1:]):
        part = passages[begin:end]
        if not part:
            continue
        if umbrella is not None and _mixed(part):
            sections.append(_shared_section(part, umbrella, start_index + len(sections)))
            continue
        sections.append(_section(part, originals, start_index + len(sections)))
    return sections


def chunks_from_sections(sections: list[Section], *, filename: str) -> list[Chunk]:
    """Shape finished sections into response records, in the order given."""
    return sections_for_chunking(sections, filename=filename)


def _by_group(passages: list[PreparedSentence]) -> list[tuple[int, list[PreparedSentence]]]:
    groups: list[tuple[int, list[PreparedSentence]]] = []
    for passage in passages:
        if passage.group is None:
            continue
        if groups and groups[-1][0] == passage.group:
            groups[-1][1].append(passage)
            continue
        groups.append((passage.group, [passage]))
    return groups


def _assemble_group(sentences: list[PreparedSentence], cuts: list[int]) -> list[PreparedSentence]:
    starts = sorted({0, *(cut for cut in cuts if 0 < cut < len(sentences))})
    starts.append(len(sentences))
    assembled: list[PreparedSentence] = []
    for begin, end in zip(starts, starts[1:]):
        part = sentences[begin:end]
        if part:
            assembled.append(_joined(part))
    return assembled


def _joined(part: list[PreparedSentence]) -> PreparedSentence:
    first = part[0]
    text = _join_group(part)
    return PreparedSentence(
        text=text,
        embed_text=_embed_text(titled_path(first.title, first.headings), text),
        headings=list(first.headings),
        heading=first.heading,
        subheading=first.subheading,
        page=first.page,
        section_index=first.section_index,
        section_id=first.section_id,
        file_id=first.file_id,
        kind=first.kind,
        order=first.order,
        group=None,
        compare_text=_join_compare(part),
        title=first.title,
    )


def _join_compare(part: list[PreparedSentence]) -> str | None:
    if all(passage.compare_text is None for passage in part):
        return None
    return "\n".join(passage.vector_text for passage in part)


def _join_group(part: list[PreparedSentence]) -> str:
    if part[0].kind != "list":
        return " ".join(passage.text for passage in part)
    texts = [part[0].text]
    for passage in part[1:]:
        texts.append(_without_repeated_lead(part[0].text, passage.text))
    return "\n".join(text for text in texts if text)


def _without_repeated_lead(first: str, later: str) -> str:
    """Drop a lead-in that was repeated onto a later run of the same list."""
    lead: list[str] = []
    for line in first.split("\n"):
        if _LIST_ITEM.match(line):
            break
        lead.append(line)
    if not any(line.strip() for line in lead):
        return later
    lines = later.split("\n")
    if lines[: len(lead)] != lead:
        return later
    rest = lines[len(lead) :]
    if rest and not rest[0].strip():
        rest = rest[1:]
    return "\n".join(rest)


def _section(part: list[PreparedSentence], originals: dict[str, Section], index: int) -> Section:
    first = part[0]
    original = originals.get(first.section_id)
    if len(part) == 1 and original is not None and original.media and first.kind in _MEDIA_KINDS:
        return original.model_copy(
            update={
                "index": index,
                "data": first.text,
                "headings": list(first.headings),
                "heading": first.heading,
                "subheading": first.subheading,
                "page": first.page if first.page is not None else original.page,
            }
        )
    kinds = {passage.kind for passage in part}
    kind: SectionKind = kinds.pop() if len(kinds) == 1 else "text"
    return Section(
        file_id=first.file_id,
        index=index,
        kind=kind,
        title=first.title,
        headings=list(first.headings),
        heading=first.heading,
        subheading=first.subheading,
        page=first.page,
        data=_join_chunk(part),
    )


def _mixed(part: list[PreparedSentence]) -> bool:
    return any(passage.headings != part[0].headings for passage in part[1:])


def _shared_section(part: list[PreparedSentence], umbrella: Umbrella, index: int) -> Section:
    first = part[0]
    kinds = {passage.kind for passage in part}
    kind: SectionKind = kinds.pop() if len(kinds) == 1 else "text"
    texts: list[str] = []
    previous: list[str] | None = None
    for passage in part:
        titles = passage.headings[len(umbrella.headings) :] if passage.headings != previous else []
        texts.append("\n".join([*titles, passage.text]))
        previous = passage.headings
    return Section(
        file_id=first.file_id,
        index=index,
        kind=kind,
        title=first.title,
        headings=list(umbrella.headings),
        heading=umbrella.heading,
        subheading=umbrella.subheading,
        page=first.page,
        data="\n\n".join(texts),
    )


def _join_chunk(part: list[PreparedSentence]) -> str:
    if len(part) == 1:
        return part[0].text
    return "\n\n".join(passage.text for passage in part)
