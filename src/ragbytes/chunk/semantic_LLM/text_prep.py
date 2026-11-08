"""Turn document text into numbered sentences for a later split-point question."""

import re
from dataclasses import dataclass

from ragbytes.chunk.semantic_embed.embed_prep import (
    _join_lines,
    _newlines,
    _split_sentences,
)
from ragbytes.schemas import Section, SectionKind

_WHOLE_KINDS = frozenset({"image", "chart", "complex"})


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
    """Split each section into sentences and keep that section's metadata on each one.

    Images, charts, and complex regions are left out. They have no prose to
    number. The returned list is in file order.
    """
    tagged: list[TaggedSentence] = []
    for section in sorted(sections, key=lambda section: section.index):
        if section.kind in _WHOLE_KINDS:
            continue
        for sentence in _document_sentences(section.data):
            tagged.append(
                TaggedSentence(
                    text=sentence,
                    title=section.title,
                    headings=list(section.headings),
                    heading=section.heading,
                    subheading=section.subheading,
                    page=section.page,
                    kind=section.kind,
                    file_id=section.file_id,
                )
            )
    return tagged


def _document_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for paragraph in re.split(r"\n\s*\n", _newlines(text).strip()):
        line = _join_lines(paragraph)
        if not line:
            continue
        sentences.extend(_split_sentences(line))
    return sentences