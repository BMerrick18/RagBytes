"""Turn a document into prose sentences and whole figures for a later model call."""

import re
from dataclasses import dataclass

from ragbytes.chunk.assemble import _media_is_text, titled_path
from ragbytes.chunk.semantic_embed.embed_prep import (
    _LIST_ITEM,
    _join_lines,
    _lead_repeats,
    _newlines,
    _split_sentences,
)
from ragbytes.schemas import Section, SectionKind

_FIGURE_KINDS = frozenset({"image", "chart", "table", "complex"})
_BARE_MARKERS = frozenset({"[Image]", "[Chart]", "[Complex]"})
# A bullet run inside ordinary text. Numbered lines stay sentences.
_BULLET_LINE = re.compile(r"^[ \t]*[-*•][ \t]+\S")
# A heading or a colon lead under this may sit with the figure or list it names.
_SHORT_HEADING = 200
_CAPTION_CHARS = 100
# Picture types the figure-title call can be shown.
_VISION_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})


@dataclass
class NumberedSentences:
    """The sentences we will slice, and the numbered view the model reads.

    ``sentences`` is the source of truth. ``numbered`` is only for the prompt.
    """

    sentences: list[str]
    numbered: str


def number_sentences(text: str) -> NumberedSentences:
    """Split ``text`` into sentences and number them from 0.

    A blank line starts a new paragraph before any sentence split, so a
    heading with no period stays its own item. Wrapped lines inside a
    paragraph are joined first.
    """
    sentences = _document_sentences(text)
    return NumberedSentences(sentences=sentences, numbered=numbered_lines(sentences))


@dataclass
class TaggedSentence:
    """One original sentence, with the section facts the model is not shown.

    ``title`` is the document title. ``headings`` is that section's path,
    outer heading first. ``topic`` is not stored here: the model chooses it
    for a whole slice later.
    """

    text: str
    title: str | None
    headings: list[str]
    heading: str | None
    subheading: str | None
    page: int | None
    kind: SectionKind
    file_id: str


def tag_sentences(sections: list[Section]) -> list[TaggedSentence]:
    """Split each prose section into sentences and keep that section's metadata.

    Images, charts, tables, and complex regions are left out. Each of those
    is its own chunk. A list is one block, so its items stay together. The
    returned list is in file order.
    """
    tagged: list[TaggedSentence] = []
    for section in sorted(sections, key=lambda section: section.index):
        if section.kind in _FIGURE_KINDS:
            continue
        for sentence in _section_sentences(section):
            tagged.append(_tagged(section, sentence))
    return tagged


@dataclass
class ProseRun:
    """Consecutive prose sentences that sit between figures.

    The model may cut these into several topics. A figure is never one of
    these sentences.
    """

    sentences: list[TaggedSentence]


@dataclass
class FigureUnit:
    """One image, chart, table, or complex region, in file order.

    A diagram extracted from a page is an image section, so it arrives here.
    """

    section: Section


def segment_sections(sections: list[Section]) -> list[ProseRun | FigureUnit]:
    """Split a document into prose runs and whole figures, in file order.

    A figure ends the prose run before it and starts a new one after it, so
    the topic call never sees it among the sentences. A bare ``[Image]``,
    ``[Chart]``, or ``[Complex]`` with no bytes is left out and does not
    split the prose around it. Text, lists, and code stay prose. A list is
    one block, so a chunk starts before or after the list, not on each item.
    """
    units: list[ProseRun | FigureUnit] = []
    prose: list[TaggedSentence] = []

    def flush() -> None:
        if prose:
            units.append(ProseRun(list(prose)))
            prose.clear()

    for section in sorted(sections, key=lambda section: section.index):
        if section.kind in _FIGURE_KINDS:
            if not _keep_figure(section):
                continue
            flush()
            units.append(FigureUnit(section))
            continue
        for sentence in _section_sentences(section):
            prose.append(_tagged(section, sentence))
    flush()
    return units


def figure_message(section: Section) -> tuple[str, bytes | None, str | None]:
    """Return the text and picture one figure-title call sends.

    A picture is returned only for png, jpeg, gif, or webp bytes. The text
    sent with a picture is the label, the document title and heading path,
    and the page. A bare marker is left out of that text. A table or a chart
    with no picture sends its own text and not the headings around it.
    """
    body = _figure_body(section)
    media, media_type = _vision_bytes(section)
    if media is None:
        return body, None, None
    lines: list[str] = []
    if body:
        lines.append(body)
    path = " > ".join(titled_path(section.title, section.headings))
    if path:
        lines.append(path)
    if section.page is not None:
        lines.append(f"Page {section.page}")
    return "\n".join(lines), media, media_type


def _tagged(section: Section, sentence: str) -> TaggedSentence:
    return TaggedSentence(
        text=sentence,
        title=section.title,
        headings=list(section.headings),
        heading=section.heading,
        subheading=section.subheading,
        page=section.page,
        kind=section.kind,
        file_id=section.file_id,
    )


def _keep_figure(section: Section) -> bool:
    """A figure stays when it has bytes, or text that is more than a bare marker.

    A table has no marker. Its text is enough. A bare ``[Image]``, ``[Chart]``,
    or ``[Complex]`` with no bytes is left out.
    """
    if section.media:
        return True
    label = section.data.strip()
    if not label:
        return False
    if section.kind == "table":
        return True
    return label not in _BARE_MARKERS


def _figure_body(section: Section) -> str:
    body = section.data.strip()
    if body in _BARE_MARKERS:
        body = ""
    if section.media and _media_is_text(section.media_type):
        decoded = section.media.decode("utf-8").strip()
        if decoded and decoded != body:
            body = "\n".join(part for part in (body, decoded) if part)
    return body


def _vision_bytes(section: Section) -> tuple[bytes | None, str | None]:
    if not section.media or _media_is_text(section.media_type):
        return None, None
    media_type = section.media_type or "image/png"
    if media_type == "image/jpg":
        media_type = "image/jpeg"
    if media_type not in _VISION_TYPES:
        return None, None
    return section.media, media_type


def numbered_lines(
    sentences: list[str], headings: list[list[str]] | None = None
) -> str:
    """Number each entry from 0. Further lines of an entry have no index.

    A list or a block of code is one entry, so its lines have no index. When
    ``headings`` is given, a heading is written once, above the first entry
    that sits under it.
    """
    lines: list[str] = []
    previous: list[str] | None = None
    for index, sentence in enumerate(sentences):
        if headings is not None:
            path = headings[index]
            if path != previous:
                if path:
                    lines.append("# " + " > ".join(path))
                previous = path
        parts = sentence.splitlines() or [""]
        lines.append(f"[{index}] {parts[0].rstrip()}")
        lines.extend(part.rstrip() for part in parts[1:])
    return "\n".join(lines)


def absorb_captions(units: list[ProseRun | FigureUnit]) -> list[ProseRun | FigureUnit]:
    """Write a short caption that introduces a figure onto that figure.

    A colon lead, a one-line label, or a one-line pointer to a picture is
    taken from the end of the prose run in front of the figure. The figure
    keeps its own chunk. A normal sentence stays in the prose.
    """
    units = list(units)
    absorbed: list[ProseRun | FigureUnit] = []
    index = 0
    while index < len(units):
        unit = units[index]
        following = units[index + 1] if index + 1 < len(units) else None
        if isinstance(unit, ProseRun) and isinstance(following, FigureUnit):
            caption, rest = _peel_caption(unit.sentences)
            if caption:
                following = FigureUnit(_with_caption(following.section, caption))
                units[index + 1] = following
            if rest:
                absorbed.append(ProseRun(rest))
            index += 1
            continue
        absorbed.append(unit)
        index += 1
    return absorbed


def _section_sentences(section: Section) -> list[str]:
    """The entries the model may cut between.

    A list's items share one entry. A one-line label or a colon lead stays
    on that entry. A bullet run inside ordinary text is one entry too.
    Code keeps its lines and is one entry. Any other text is split as prose.
    """
    if section.kind == "code":
        return _code_block(section.data)
    if section.kind == "list":
        return _list_units(section.data)
    return _prose_units(section.data)


def _list_units(text: str) -> list[str]:
    """Return the lead sentences and one block holding every item.

    The items stay one entry, nested items included, so a chunk cannot
    start on each of them. A one-line lead that ends with a colon stays at
    the top of that block. A list with no markers is read as prose.
    """
    lines = _newlines(text).strip("\n").split("\n")
    first = next((index for index, line in enumerate(lines) if _LIST_ITEM.match(line)), None)
    if first is None:
        return _document_sentences(text)
    lead = [line.rstrip() for line in lines[:first]]
    while lead and not lead[-1].strip():
        lead.pop()
    body = [line.rstrip() for line in lines[first:] if line.strip()]
    units = _document_sentences("\n".join(lead)) if any(line.strip() for line in lead) else []
    block = "\n".join(body)
    if units and _is_list_label(units[-1]):
        block = f"{units.pop()}\n{block}"
    if block:
        units.append(block)
    return units


def _prose_units(text: str) -> list[str]:
    """Split prose, and keep each bullet run as one block.

    A line that only continues a bullet stays on that run. A one-line label
    or a colon lead directly above the run stays on the block. Numbered
    lines stay sentences.
    """
    units: list[str] = []
    prose: list[str] = []
    body: list[str] = []

    def flush_prose() -> None:
        if any(line.strip() for line in prose):
            units.extend(_document_sentences("\n".join(prose)))
        prose.clear()

    def flush_body() -> None:
        if not body:
            return
        block = "\n".join(line.rstrip() for line in body if line.strip())
        body.clear()
        if block and units and _is_list_label(units[-1]):
            block = f"{units.pop()}\n{block}"
        if block:
            units.append(block)

    in_list = False
    for line in _newlines(text).strip("\n").split("\n"):
        if _BULLET_LINE.match(line):
            if not in_list:
                flush_prose()
                in_list = True
            body.append(line)
            continue
        if in_list and line.startswith((" ", "\t")) and line.strip():
            body.append(line)
            continue
        if in_list:
            flush_body()
            in_list = False
        prose.append(line)
    if in_list:
        flush_body()
    flush_prose()
    return units


def _code_block(text: str) -> list[str]:
    """One block, with the source line breaks left as they are."""
    block = _newlines(text).strip("\n")
    if not block.strip():
        return []
    return [block]


def _is_list_label(text: str) -> bool:
    """A one-line name or a colon lead that belongs on the list under it."""
    if "\n" in text:
        return False
    if _lead_repeats([text]):
        return True
    line = " ".join(text.split())
    if not line or len(line) > _CAPTION_CHARS:
        return False
    return not line.endswith((".", "!", "?"))


def _peel_caption(sentences: list[TaggedSentence]) -> tuple[str, list[TaggedSentence]]:
    """Take caption lines off the end of a prose run, leaving the rest."""
    kept = list(sentences)
    peeled: list[TaggedSentence] = []
    while kept and _is_caption(kept[-1]):
        peeled.append(kept.pop())
    peeled.reverse()
    return "\n".join(sentence.text for sentence in peeled), kept


def _is_caption(sentence: TaggedSentence) -> bool:
    """A label, a colon lead, or a one-line pointer to the figure after it."""
    if sentence.kind in {"code", "list"} or "\n" in sentence.text:
        return False
    text = " ".join(sentence.text.split())
    if not text or len(text) > _SHORT_HEADING:
        return False
    if text.endswith(":"):
        return True
    if text.endswith((".", "!", "?")):
        lowered = text.lower()
        return len(text) <= _CAPTION_CHARS and (
            "http://" in lowered or "https://" in lowered or lowered.startswith(("and now", "see "))
        )
    return len(text) <= _CAPTION_CHARS


def _with_caption(section: Section, caption: str) -> Section:
    body = section.data.strip()
    data = f"{caption}\n{body}" if body else caption
    return section.model_copy(update={"data": data})


def _document_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for paragraph in re.split(r"\n\s*\n", _newlines(text).strip()):
        line = _join_lines(paragraph)
        if not line:
            continue
        sentences.extend(_split_sentences(line))
    return sentences