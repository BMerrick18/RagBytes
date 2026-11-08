"""Prepare extracted sections as passages ready to embed."""

import re
from dataclasses import dataclass

from ragbytes.chunk.assemble import titled_path
from ragbytes.chunk.semantic_embed.styles import BALANCED, Style
from ragbytes.chunk.simple import _split_table, prepared_sections
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
# Bullets, ``1.`` / ``1)``, multi-level numbers such as ``1.8.`` and ``7.2``, a bare
# number such as ``12``, and letter markers such as ``(a)``, ``a)``, and ``i.``.
_LIST_MARKER = (
    r"[-*•]"
    r"|\d+(?:\.\d+)+\.?"
    r"|\d{1,9}[.)]"
    r"|\d{1,9}"
    r"|\([A-Za-z]{1,8}\)"
    r"|[A-Za-z]\)"
    r"|[ivxlcdm]+\."
    r"|[IVXLCDM]+\."
    r"|[a-z]\."
)
_LIST_ITEM = re.compile(rf"^([ \t]*)({_LIST_MARKER})([ \t]+)(\S.*?)\s*$")
_NUMBERED_CLAUSE = re.compile(r"^\d+(?:\.\d+)*\.?\s")
_CLOSERS = "\"'”’)]}"
_OPENERS = "\"'“‘"
_WHOLE = frozenset({"table", "code", "image", "chart", "complex"})
# A one-line lead ending like ``Bring the kit:`` is repeated on later runs.
# Anything longer is ordinary prose placed once, ahead of the list.
_LEAD_LIMIT = 200
# List runs aim at this share of the style maximum, then the first pass decides the cuts.
_LIST_PACK = 0.75


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


def prepare_sentences(sections: list[Section], style: Style = BALANCED) -> list[HeadingPassages]:
    """Turn extracted sections into one embedding umbrella per heading path.

    Sections are read in file order. A run of sections with the same heading
    and subheading shares an umbrella. A short label just before a figure stays
    on that figure, and a bare ``[Image]``, ``[Chart]``, or ``[Complex]`` is
    left out. A paragraph that fits the style maximum stays whole. A longer
    paragraph is split into sentences, and those sentences go to ``to_embed``.
    A blank line still starts a new paragraph. Lines that start a numbered
    clause keep the newline between them. A list that fits the maximum stays
    whole too. A longer list is cut between items into runs of about three
    quarters of that maximum, and those runs go to ``to_embed``. A nested
    entry stays with its parent until that parent no longer fits a run. A
    table, a block of code, an image, a chart, and a complex region stay in
    ``whole``.

    Every piece keeps the heading path of the section it came from, for the
    finished chunk. The passes compare passage text without that path.
    """
    scopes: list[HeadingPassages] = []
    order = 0
    for section in prepared_sections(sections):
        for block in _blocks(section, style.max_chars):
            if not block.texts:
                continue
            scope = _scope_for(scopes, section)
            split = block.split and len(block.texts) > 1
            group_id = _next_group(scope) if split else None
            compares = block.compare or [None] * len(block.texts)
            for text, compare in zip(block.texts, compares, strict=True):
                passage = _from_section(section, text, order, group_id)
                if block.kind is not None:
                    passage.kind = block.kind
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
    ``kind`` overrides the section kind, so a long list lead is ordinary prose.
    """

    texts: list[str]
    split: bool
    compare: list[str | None] | None = None
    kind: SectionKind | None = None


def _blocks(section: Section, max_chars: int) -> list[_Block]:
    if section.kind == "list":
        return _list_blocks(section.data, max_chars)
    if section.kind in _WHOLE:
        text = section.data.strip("\n") if section.kind == "code" else section.data.strip()
        return [_Block([text], split=False)] if text.strip() else []
    return _prose_blocks(section.data, max_chars)


def _prose_blocks(data: str, max_chars: int) -> list[_Block]:
    """Keep a paragraph that fits the maximum whole, and split only a longer one."""
    blocks: list[_Block] = []
    for paragraph in re.split(r"\n\s*\n", _newlines(data).strip()):
        line = _join_lines(paragraph)
        if not line:
            continue
        if len(line) <= max_chars:
            blocks.append(_Block([line], split=False))
            continue
        sentences = _split_sentences(line)
        blocks.append(_Block(sentences, split=len(sentences) > 1))
    return blocks


def _join_lines(paragraph: str) -> str:
    """Join wrapped lines. A numbered clause keeps the newline in front of it."""
    lines = [" ".join(line.split()) for line in paragraph.split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    pieces = [lines[0]]
    for line in lines[1:]:
        pieces.append(("\n" if _NUMBERED_CLAUSE.match(line) else " ") + line)
    return "".join(pieces)


@dataclass
class _ListItem:
    indent: int
    depth: int
    lines: list[str]


def _list_blocks(data: str, max_chars: int) -> list[_Block]:
    """Return a list that fits the maximum as one chunk, or cut a longer one between items.

    A lead-in is repeated on later runs only when it is one line, ends with a
    colon or semicolon, and is under about 200 characters. A longer lead is
    prose placed once, ahead of the first run, and does not count toward the
    run size. The embedding text of a run leaves a repeated lead out. A nested
    entry stays on its parent while the parent fits a run. A list with no
    items is read as prose.
    """
    text = _newlines(data).strip("\n")
    if not text.strip():
        return []
    lead, items = _parse_list(text)
    if not items:
        return _prose_blocks(text, max_chars)
    repeats = _lead_repeats(lead)
    visible = _format_list(lead, items)
    if len(visible) <= max_chars:
        return _lead_and_list(lead, [_format_list(lead if repeats else [], items)], repeats and bool(lead), max_chars)
    target = max(1, int(max_chars * _LIST_PACK))
    runs = _greedy(_expand(items, target), target)
    repeated = lead if repeats else []
    pieces = [_format_list(repeated, run) for run in runs]
    return _lead_and_list(lead, pieces, repeats, max_chars)


def _lead_and_list(lead: list[str], pieces: list[str], repeats: bool, max_chars: int) -> list[_Block]:
    """Place a long lead before the list runs. A short colon lead stays on each run."""
    blocks: list[_Block] = []
    if lead and not repeats:
        prose = _prose_blocks("\n".join(lead), max_chars)
        for block in prose:
            block.kind = "text"
        blocks.extend(prose)
    compare = [_without_lead(lead, piece) for piece in pieces] if repeats and lead else None
    blocks.append(_Block(pieces, split=len(pieces) > 1, compare=compare))
    return blocks


def _lead_repeats(lead: list[str]) -> bool:
    """A one-line colon lead under about 200 characters is repeated on later runs."""
    if len(lead) != 1:
        return False
    line = lead[0].strip()
    if not line or len(line) > _LEAD_LIMIT:
        return False
    core = line.rstrip(_CLOSERS).rstrip()
    return core.endswith((":", ";", ":-"))


def _without_lead(lead: list[str], piece: str) -> str:
    """Return a list run's items, without the lead-in lines written above them."""
    return "\n".join(piece.split("\n")[len(lead) :])


def _parse_list(text: str) -> tuple[list[str], list[_ListItem]]:
    """Split a list into its lead-in and its top-level items.

    A deeper number, such as ``1.8.`` under ``1.``, is a child of the item
    above it. So is a marker indented further. A bare number or a letter
    marker at the same depth starts its own item.
    """
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
        depth = _number_depth(match.group(2))
        if items and (indent > items[-1].indent or (depth > items[-1].depth > 0)):
            items[-1].lines.append(line)
            continue
        items.append(_ListItem(indent=indent, depth=depth, lines=[line]))
    return lead, items


def _number_depth(marker: str) -> int:
    """How many numeric parts a marker has. Bullets and letters are 0."""
    match = re.fullmatch(r"(\d+(?:\.\d+)*)\.?", marker)
    if match is None:
        return 0
    return match.group(1).count(".") + 1


def _expand(items: list[_ListItem], target: int) -> list[_ListItem]:
    """Open an item into its nested markers when the item itself exceeds ``target``."""
    expanded: list[_ListItem] = []
    for item in items:
        parts = _nested_parts(item)
        if len(parts) > 1 and _measure([], [item]) > target:
            expanded.extend(parts)
        else:
            expanded.append(item)
    return expanded


def _nested_parts(item: _ListItem) -> list[_ListItem]:
    """Split an item's lines at each nested marker."""
    parts: list[list[str]] = []
    for line in item.lines:
        if parts and _LIST_ITEM.match(line):
            parts.append([line])
            continue
        if not parts:
            parts.append([])
        parts[-1].append(line)
    if len(parts) <= 1:
        return [item]
    return [_ListItem(indent=item.indent, depth=item.depth, lines=part) for part in parts]


def _greedy(items: list[_ListItem], target: int) -> list[list[_ListItem]]:
    """Pack items until the next one would pass ``target``. The lead is not included."""
    if not items:
        return []
    runs: list[list[_ListItem]] = []
    current: list[_ListItem] = []
    for item in items:
        if current and _measure([], current + [item]) > target:
            runs.append(current)
            current = []
        current.append(item)
    if current:
        runs.append(current)
    return runs


def _measure(lead: list[str], items: list[_ListItem]) -> int:
    return len(_format_list(lead, items))


def _format_list(lead: list[str], items: list[_ListItem]) -> str:
    parts = ["\n".join(lead)] if lead else []
    parts.extend("\n".join(item.lines) for item in items)
    return "\n".join(parts)


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


def split_to_limit(text: str, kind: str, limit: int) -> list[str]:
    """Split one passage so each piece fits ``limit``.

    A list breaks between items, a table between rows, and code at blank
    lines. Prose breaks between sentences, then words. A piece with no break
    inside it is cut at ``limit``.
    """
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    if kind == "list":
        pieces = _split_list_text(text, limit)
    elif kind == "table":
        pieces = _split_table_text(text, limit)
    elif kind == "code":
        pieces = _split_code_text(text, limit)
    else:
        pieces = _split_prose(text, limit)
    return _enforce_limit(pieces, limit)


def _split_list_text(text: str, limit: int) -> list[str]:
    lead, items = _parse_list(text)
    if not items:
        return _split_prose(text, limit)
    repeats = bool(lead) and _lead_repeats(lead)
    pieces: list[str] = []
    budget = limit
    if repeats:
        budget = max(1, limit - len("\n".join(lead)) - 1)
    elif lead:
        lead_text = "\n".join(lead)
        pieces.extend(_split_prose(lead_text, limit) if len(lead_text) > limit else [lead_text])
    atoms: list[_ListItem] = []
    for item in items:
        atoms.extend(_nested_parts(item))
    for run in _greedy(atoms, budget):
        piece = _format_list(lead if repeats else [], run)
        if len(piece) <= limit:
            pieces.append(piece)
            continue
        body = "\n".join("\n".join(item.lines) for item in run)
        pieces.extend(_split_prose(body, limit))
    return pieces


def _split_table_text(text: str, limit: int) -> list[str]:
    pieces: list[str] = []
    for piece in _split_table(text, limit):
        if len(piece) <= limit:
            pieces.append(piece)
        else:
            pieces.extend(_split_newlines(piece, limit))
    return pieces


def _split_code_text(text: str, limit: int) -> list[str]:
    blocks = [block for block in re.split(r"\n\s*\n", text.strip("\n")) if block]
    return _pack_pieces(blocks, limit, "\n\n", _split_newlines)


def _split_prose(text: str, limit: int) -> list[str]:
    sentences = _split_sentences(text)
    if len(sentences) <= 1:
        return _split_words(text, limit)
    return _pack_pieces(sentences, limit, " ", _split_words)


def _split_newlines(text: str, limit: int) -> list[str]:
    return _pack_pieces(text.split("\n"), limit, "\n", _split_words)


def _pack_pieces(parts: list[str], limit: int, sep: str, finer) -> list[str]:
    pieces: list[str] = []
    current: list[str] = []
    for part in parts:
        if not part:
            continue
        if current and len(sep.join([*current, part])) > limit:
            pieces.append(sep.join(current))
            current = []
        if not current and len(part) > limit:
            pieces.extend(finer(part, limit))
            continue
        current.append(part)
    if current:
        pieces.append(sep.join(current))
    return pieces


def _split_words(text: str, limit: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for word in text.split(" "):
        if not word and not current:
            continue
        candidate = word if not current else f"{current} {word}"
        if word and len(candidate) <= limit:
            current = candidate
            continue
        if current:
            pieces.append(current)
            current = ""
        if not word:
            continue
        if len(word) <= limit:
            current = word
        else:
            pieces.extend(_hard_cut(word, limit))
    if current:
        pieces.append(current)
    return pieces


def _enforce_limit(pieces: list[str], limit: int) -> list[str]:
    fitted: list[str] = []
    for piece in pieces:
        if not piece:
            continue
        if len(piece) <= limit:
            fitted.append(piece)
        else:
            fitted.extend(_hard_cut(piece, limit))
    return fitted


def _hard_cut(text: str, limit: int) -> list[str]:
    if limit < 1:
        return [text]
    return [text[index : index + limit] for index in range(0, len(text), limit)]
