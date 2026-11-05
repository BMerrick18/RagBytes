"""Chunk along the document's heading tree."""

from dataclasses import dataclass, field

from ragbytes.chunk.assemble import sections_for_chunking
from ragbytes.chunk.simple import WHOLE_KINDS, piece_texts, prepared_sections
from ragbytes.schemas import Chunk, Section

CHUNK_SIZE = 2000


@dataclass
class _Block:
    """Text under one heading path, with the sections it came from."""

    path: list[str]
    members: list[Section] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(self.texts)

    def add(self, member: Section, text: str) -> None:
        if not self.members or self.members[-1] is not member:
            self.members.append(member)
        self.texts.append(text)


def chunk_structured(sections: list[Section], *, filename: str) -> list[Chunk]:
    """Make one chunk per heading and subheading, and split a chunk only when it is too long.

    Sections that share a heading path form one block, even across a page
    break or around a figure, however short that text is. A heading or
    subheading change starts a new chunk. There is no minimum length: a
    subsection of one line stays its own chunk, and its ``heading`` and
    ``subheading`` stay in the metadata.

    A block longer than about 2,000 characters is split into pieces of even
    size, between its paragraphs, lists, and tables where it can, and inside
    a single element only when that element alone is too long. When that cut
    splits a paragraph in two, the next piece repeats the paragraph's last
    sentence, or about 200 characters when that sentence is longer than about
    300. A long list is split between items, and a long table between rows,
    repeating the table's caption and header. Each piece keeps the same
    heading and subheading.

    Images, charts, and complex regions are their own chunks and do not break
    the text of their section. A figure with no description, or a complex
    region with no text yet, is left out.
    """
    ordered = prepared_sections(sections)
    figures = [section for section in ordered if section.kind in WHOLE_KINDS]
    flowing = [section for section in ordered if section.kind not in WHOLE_KINDS and section.data.strip()]
    records: list[Section] = list(figures)
    records.extend(_record(block) for block in _fitted(_blocks(flowing)))
    return sections_for_chunking(records, filename=filename)


def _blocks(sections: list[Section]) -> list[_Block]:
    blocks: list[_Block] = []
    for section in sections:
        if not blocks or blocks[-1].path != section.headings:
            blocks.append(_Block(path=list(section.headings)))
        blocks[-1].add(section, section.data.strip())
    return blocks


def _fitted(blocks: list[_Block]) -> list[_Block]:
    fitted: list[_Block] = []
    for block in blocks:
        if len(block.text) <= CHUNK_SIZE:
            fitted.append(block)
        else:
            fitted.extend(_split_block(block))
    return fitted


def _split_block(block: _Block) -> list[_Block]:
    """Cut a long block into pieces of about even size, each within the limit."""
    units = [
        (member, text)
        for member in block.members
        for text in piece_texts(member, limit=CHUNK_SIZE, sentence_overlap=member.kind == "text")
    ]
    remaining = sum(len(text) for _, text in units) + 2 * (len(units) - 1)
    pieces_left = -(-remaining // CHUNK_SIZE)
    pieces = [_Block(path=block.path)]
    size = 0
    for member, text in units:
        added = len(text) + (2 if pieces[-1].texts else 0)
        target = remaining / pieces_left
        if pieces[-1].texts and (size + added > CHUNK_SIZE or size + added - target > target - size):
            remaining -= size + 2
            pieces_left = max(pieces_left - 1, -(-remaining // CHUNK_SIZE), 1)
            pieces.append(_Block(path=block.path))
            size = 0
            added = len(text)
        pieces[-1].add(member, text)
        size += added
    return pieces


def _record(block: _Block) -> Section:
    first = block.members[0]
    kinds = {member.kind for member in block.members}
    heading, subheading = _titles(first, block.path)
    return first.model_copy(
        update={
            "kind": kinds.pop() if len(kinds) == 1 else "text",
            "data": block.text,
            "headings": list(block.path),
            "heading": heading,
            "subheading": subheading,
            "media": None,
            "media_type": None,
        }
    )


def _titles(section: Section, path: list[str]) -> tuple[str | None, str | None]:
    """Keep the section's heading and subheading, filling either from the path when it is blank."""
    heading = section.heading
    subheading = section.subheading
    if heading is None and path:
        heading = path[0]
    if subheading is None and len(path) > 1 and path[-1] != heading:
        subheading = path[-1]
    return heading, subheading
