"""Prepare extracted sections as passages ready to embed."""

import re
from dataclasses import dataclass

from ragbytes.chunk.assemble import titled_path
from ragbytes.chunk.simple import prepared_sections
from ragbytes.schemas import Section, SectionKind

# A period after one of these stays in the sentence. Single initials such as
# ``A.`` and ``U.S.`` are handled separately, as is a dotted chain such as ``Ph.D.``.
_ABBREVIATIONS = frozenset(
    {
        "al",
        "approx",
        "apr",
        "aug",
        "ca",
        "cf",
        "co",
        "corp",
        "dec",
        "dept",
        "dr",
        "ed",
        "eds",
        "eg",
        "eq",
        "eqs",
        "esq",
        "etc",
        "feb",
        "fig",
        "figs",
        "ie",
        "inc",
        "jan",
        "jr",
        "jul",
        "jun",
        "ltd",
        "mar",
        "mr",
        "mrs",
        "ms",
        "no",
        "nos",
        "nov",
        "oct",
        "pp",
        "prof",
        "ref",
        "refs",
        "rev",
        "sec",
        "secs",
        "sep",
        "sept",
        "sr",
        "st",
        "viz",
        "vol",
        "vols",
        "vs",
    }
)
_LIST_ITEM = re.compile(r"^([ \t]*)((?:[-*•]|\d{1,9}[.)])[ \t]+)(\S.*?)\s*$")
_CLOSERS = "\"'”’)]}"
_OPENERS = "\"'“‘"
_WHOLE = frozenset({"table", "code", "image", "chart", "complex"})
# A list this size is one subject. A longer list is cut between items into runs of about this size.
_SMALL_LIST_ITEMS = 8
_SMALL_LIST_CHARS = 1000
# A paragraph this size is one subject. A longer one has room for the subject to change, so it is split into sentences.
_LONG_PARAGRAPH_CHARS = 1000


@dataclass
class PreparedSentence:
    """One passage, still under its heading path.

    ``text`` is a small paragraph, a sentence from a very long paragraph, or a
    block such as a list or a table. ``embed_text`` is the document title and
    heading path, a blank line, then ``text``, as the finished chunk will carry it. A document
    with no headings uses ``text`` alone. Neither pass embeds ``embed_text``:
    every passage under one heading shares the path, so it would only pull the
    scores together. ``heading`` and ``subheading`` are the titles from the
    source section, copied unchanged.

    ``order`` is this passage's place in the file, counting from 0. ``group``
    is set when this passage was split from a long block. Passages that share
    a group are embedded in the first pass to decide where that block is cut.
    A passage that is already one section has no group.

    ``compare_text`` is what the passes embed when it differs from ``text``.
    A run of a long list carries the list's lead-in so the chunk reads well,
    but the lead-in is left out here so every run does not look alike.
    """

    text: str
    embed_text: str
    headings: list[str]
    heading: str | None
    subheading: str | None
    page: int | None
    section_index: int
    section_id: str
    file_id: str
    kind: SectionKind
    order: int
    group: int | None
    compare_text: str | None = None
    title: str | None = None

    @property
    def vector_text(self) -> str:
        """The text both embedding passes send for this passage."""
        return self.compare_text if self.compare_text is not None else self.text


@dataclass
class HeadingPassages:
    """Both embedding passes for one heading path.

    ``headings`` is that path, outer title first. ``heading`` and
    ``subheading`` are the titles on it. A change of either title starts a new
    umbrella, and both passes stay inside this one.

    ``to_embed`` is the first pass. Pieces that share a ``group`` come from one
    paragraph or list that was split for length. They are embedded to find the
    contextual cuts, then joined into sections and put back into ``whole`` in
    file order. ``whole`` is the second pass: neighbours are embedded, and a
    significant difference starts a new chunk under this same heading. Where
    the neighbours stay close, several paragraphs share one chunk.
    """

    headings: list[str]
    heading: str | None
    subheading: str | None
    to_embed: list[PreparedSentence]
    whole: list[PreparedSentence]


def prepare_sentences(sections: list[Section]) -> list[HeadingPassages]:
    """Turn extracted sections into one embedding umbrella per heading path.

    Sections are read in file order. A run of sections with the same heading
    and subheading shares an umbrella. A short label just before a figure stays
    on that figure, and a bare ``[Image]``, ``[Chart]``, or ``[Complex]`` is
    left out. A paragraph of up to about 1,000 characters stays whole, because
    a paragraph that size is one subject. A longer paragraph is split into
    sentences, where there is room for the subject to change, and those
    sentences go to ``to_embed``. A blank line still starts a new paragraph.
    A list of up to eight items and about 1,000 characters stays whole too. A
    longer list is cut between items into runs, and those runs go to
    ``to_embed``. A nested entry stays with its parent. A table, a block of
    code, an image, a chart, and a complex region stay in ``whole``.

    Every piece keeps the heading path of the section it came from, for the
    finished chunk. The passes compare passage text without that path.
    """
    scopes: list[HeadingPassages] = []
    order = 0
    for section in prepared_sections(sections):
        for block in _blocks(section):
            if not block.texts:
                continue
            scope = _scope_for(scopes, section)
            split = block.split and len(block.texts) > 1
            group_id = _next_group(scope) if split else None
            compares = block.compare or [None] * len(block.texts)
            for text, compare in zip(block.texts, compares, strict=True):
                passage = _from_section(section, text, order, group_id)
                passage.compare_text = compare if split else None
                order += 1
                if split:
                    scope.to_embed.append(passage)
                else:
                    scope.whole.append(passage)
    return scopes


def _scope_for(scopes: list[HeadingPassages], section: Section) -> HeadingPassages:
    if (
        scopes
        and scopes[-1].headings == list(section.headings)
        and scopes[-1].heading == section.heading
        and scopes[-1].subheading == section.subheading
    ):
        return scopes[-1]
    scope = HeadingPassages(
        headings=list(section.headings),
        heading=section.heading,
        subheading=section.subheading,
        to_embed=[],
        whole=[],
    )
    scopes.append(scope)
    return scope


def _next_group(scope: HeadingPassages) -> int:
    groups = [passage.group for passage in scope.to_embed if passage.group is not None]
    if not groups:
        return 0
    return max(groups) + 1


def _from_section(section: Section, text: str, order: int, group: int | None) -> PreparedSentence:
    headings = list(section.headings)
    return PreparedSentence(
        text=text,
        embed_text=_embed_text(titled_path(section.title, headings), text),
        headings=headings,
        heading=section.heading,
        subheading=section.subheading,
        page=section.page,
        section_index=section.index,
        section_id=section.id,
        file_id=section.file_id,
        kind=section.kind,
        order=order,
        group=group,
        title=section.title,
    )


def _embed_text(headings: list[str], text: str) -> str:
    """Return the heading path and the sentence, for embedding."""
    path = " > ".join(heading for heading in headings if heading)
    if not path:
        return text
    if text == path or text.startswith(f"{path}\n"):
        return text
    return f"{path}\n\n{text}"


@dataclass
class _Block:
    """Texts from one paragraph or list. ``split`` means the block was cut for length.

    ``compare`` matches ``texts`` one for one when a piece should be embedded
    as different text, such as a list run without its repeated lead-in.
    """

    texts: list[str]
    split: bool
    compare: list[str | None] | None = None


def _blocks(section: Section) -> list[_Block]:
    if section.kind == "list":
        return _list_blocks(section.data)
    if section.kind in _WHOLE:
        text = section.data.strip("\n") if section.kind == "code" else section.data.strip()
        return [_Block([text], split=False)] if text.strip() else []
    return _prose_blocks(section.data)


def _prose_blocks(data: str) -> list[_Block]:
    """Keep a short paragraph whole, and split only a very long one into sentences."""
    blocks: list[_Block] = []
    for paragraph in re.split(r"\n\s*\n", _newlines(data).strip()):
        line = " ".join(paragraph.split())
        if not line:
            continue
        if len(line) <= _LONG_PARAGRAPH_CHARS:
            blocks.append(_Block([line], split=False))
            continue
        sentences = _split_sentences(line)
        blocks.append(_Block(sentences, split=len(sentences) > 1))
    return blocks


@dataclass
class _ListItem:
    indent: int
    lines: list[str]


def _list_blocks(data: str) -> list[_Block]:
    """Return a small list as one chunk, or cut a long list between top-level items.

    Items in a list of up to eight entries and about 1,000 characters are
    assumed to share a subject, so the list is one chunk and is not embedded
    to find a split. A longer list is cut into runs, and those runs are
    embedded to decide the boundaries. A lead-in such as ``Bring the kit:``
    stays with the list, and is repeated on each run when the list is cut. A
    nested entry stays on its parent. A list with no items is read as prose.
    """
    text = _newlines(data).strip("\n")
    if not text.strip():
        return []
    lead, items = _parse_list(text)
    if not items:
        return _prose_blocks(text)
    if len(items) <= _SMALL_LIST_ITEMS and len(text) <= _SMALL_LIST_CHARS:
        return [_Block([text], split=False)]
    pieces: list[str] = []
    cursor = 0
    for size in _even_sizes(len(items), -(-len(items) // _SMALL_LIST_ITEMS)):
        pieces.extend(_pack_list(lead, items[cursor : cursor + size]))
        cursor += size
    compare = [_without_lead(lead, piece) for piece in pieces] if lead else None
    return [_Block(pieces, split=len(pieces) > 1, compare=compare)]


def _without_lead(lead: list[str], piece: str) -> str:
    """Return a list run's items, without the lead-in lines written above them."""
    return "\n".join(piece.split("\n")[len(lead) :])


def _parse_list(text: str) -> tuple[list[str], list[_ListItem]]:
    """Split a list into its lead-in and its top-level items."""
    lead: list[str] = []
    items: list[_ListItem] = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        match = _LIST_ITEM.match(line)
        if match is None:
            if items:
                items[-1].lines.append(line)
            else:
                lead.append(line)
            continue
        indent = len(match.group(1))
        if items and indent > items[-1].indent:
            items[-1].lines.append(line)
            continue
        items.append(_ListItem(indent=indent, lines=[line]))
    return lead, items


def _pack_list(lead: list[str], items: list[_ListItem]) -> list[str]:
    """Cut one run again when its text passes about 1,000 characters."""
    if len(items) <= 1 or _measure(lead, items) <= _SMALL_LIST_CHARS:
        return [_format_list(lead, items)]
    pieces: list[str] = []
    current: list[_ListItem] = []
    for item in items:
        if current and _measure(lead, current + [item]) > _SMALL_LIST_CHARS:
            pieces.append(_format_list(lead, current))
            current = []
        current.append(item)
    if current:
        pieces.append(_format_list(lead, current))
    return pieces


def _measure(lead: list[str], items: list[_ListItem]) -> int:
    return len(_format_list(lead, items))


def _format_list(lead: list[str], items: list[_ListItem]) -> str:
    parts = ["\n".join(lead)] if lead else []
    parts.extend("\n".join(item.lines) for item in items)
    return "\n".join(parts)


def _even_sizes(total: int, groups: int) -> list[int]:
    """Divide ``total`` into ``groups`` sizes that differ by at most one."""
    base, extra = divmod(total, groups)
    return [base + (1 if index < extra else 0) for index in range(groups)]


def _split_sentences(text: str) -> list[str]:
    """Split one paragraph into sentences.

    A sentence ends at ``.``, ``!``, or ``?`` once any closing quote or
    bracket is included. The next sentence starts with a capital letter, an
    opening quote or parenthesis, or a digit that follows a word. A period in
    a decimal, a file name, an abbreviation such as ``Dr.`` or ``e.g.``, or a
    single initial such as ``A.`` or ``U.S.`` stays in the sentence. A period
    followed by a lowercase word stays in the sentence too.
    """
    if not text:
        return []
    sentences: list[str] = []
    start = 0
    index = 0
    length = len(text)
    while index < length:
        if text[index] not in ".!?":
            index += 1
            continue
        end = _closing(text, index + 1)
        if _ends_sentence(text, index, end):
            sentence = text[start:end].strip()
            if sentence:
                sentences.append(sentence)
            next_start = end
            while next_start < length and text[next_start].isspace():
                next_start += 1
            start = next_start
            index = next_start
            continue
        index += 1
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _closing(text: str, index: int) -> int:
    while index < len(text) and text[index] in _CLOSERS:
        index += 1
    return index


def _ends_sentence(text: str, mark: int, end: int) -> bool:
    if end < len(text) and not text[end].isspace():
        return False
    if text[mark] == "." and _keeps_period(text, mark):
        return False
    following = end
    while following < len(text) and text[following].isspace():
        following += 1
    if following >= len(text):
        return True
    if text[mark] in "!?":
        return True
    nxt = text[following]
    if nxt in _OPENERS:
        following += 1
        while following < len(text) and text[following].isspace():
            following += 1
        if following >= len(text):
            return True
        nxt = text[following]
    if nxt.isupper() or nxt == "(":
        return True
    return nxt.isdigit() and _word_before(text, mark).isalpha()


def _keeps_period(text: str, mark: int) -> bool:
    """A period that belongs to an abbreviation, an initial, or an acronym."""
    word = _word_before(text, mark)
    if not word:
        return False
    if len(word) == 1 or word.lower() in _ABBREVIATIONS:
        return True
    # ``Ph.D.`` continues when the next token is a single letter and a period.
    after = mark + 1
    return len(word) <= 2 and after + 1 < len(text) and text[after].isalpha() and text[after + 1] == "."


def _word_before(text: str, mark: int) -> str:
    start = mark
    while start > 0 and text[start - 1].isalpha():
        start -= 1
    return text[start:mark]


def _newlines(data: str) -> str:
    return data.replace("\r\n", "\n").replace("\r", "\n")
