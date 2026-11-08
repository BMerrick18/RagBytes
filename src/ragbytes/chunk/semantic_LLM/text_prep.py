"""Turn a document into prose sentences and whole figures for a later model call."""

import re
from dataclasses import dataclass

from ragbytes.chunk.assemble import _media_is_text, titled_path
from ragbytes.chunk.semantic_embed.embed_prep import (
    _join_lines,
    _newlines,
    _split_sentences,
)
from ragbytes.schemas import Section, SectionKind

_FIGURE_KINDS = frozenset({"image", "chart", "table", "complex"})
_BARE_MARKERS = frozenset({"[Image]", "[Chart]", "[Complex]"})
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
    lines = [f"[{index}] {sentence}" for index, sentence in enumerate(sentences)]
    return NumberedSentences(sentences=sentences, numbered="\n".join(lines))


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
    is its own chunk. The returned list is in file order.
    """
    tagged: list[TaggedSentence] = []
    for section in sorted(sections, key=lambda section: section.index):
        if section.kind in _FIGURE_KINDS:
            continue
        for sentence in _document_sentences(section.data):
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
    split the prose around it. Text, lists, and code stay prose.
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
        for sentence in _document_sentences(section.data):
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


def _document_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for paragraph in re.split(r"\n\s*\n", _newlines(text).strip()):
        line = _join_lines(paragraph)
        if not line:
            continue
        sentences.extend(_split_sentences(line))
    return sentences