"""Plain text and Markdown, normalized into sections."""

import html
import re
from collections import Counter

from bs4 import BeautifulSoup, Comment, Tag

from ragbytes.extract.html import inline_text
from ragbytes.extract.render import render_complex, render_image, render_paragraph, render_table
from ragbytes.extract.sections import (
    HeadingState,
    add_section,
    assign_indexes,
    compose_inline,
    image_from_data_uri,
    looks_like_heading,
)
from ragbytes.schemas import Section

_ATX = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*#*\s*$")
_OUTLINE = re.compile(r"^(\d+(?:\.\d+)+)\.?\s+(\S.*?)\s*$")
_UNDERLINE_H1 = re.compile(r"^={3,}\s*$")
_UNDERLINE_H2 = re.compile(r"^-{3,}\s*$")
_FENCE = re.compile(r"^(`{3,}|~{3,})")
_LIST_ITEM = re.compile(r"^([ \t]*)([-*+]|\d{1,9}[.)])[ \t]+(.*\S)\s*$")
_SEPARATOR_CELL = re.compile(r":?-{1,}:?")
_CELL_LAYOUT = re.compile(r"<(?:table|svg|canvas)\b", re.IGNORECASE)
_HTML_IMAGE = re.compile(
    r"""<img\b[^>]*\balt=["']([^"']*)["'][^>]*>|<img\b[^>]*>""",
    re.IGNORECASE,
)
_IMAGE = re.compile(r"!\[([^\]]*)\](?:\(([^)\n]*)\)|\[[^\]]*\])")
_LINK = re.compile(r"(?<!!)\[([^\]]+)\](?:\([^)\n]*\)|\[[^\]]*\])")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_STRIKE = re.compile(r"~~([^~\n]+)~~")
_BOLD = re.compile(r"\*\*([^*\n]+)\*\*|__([^_\n]+)__")
_ITALIC_STAR = re.compile(r"(?<!\*)\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)")
_ITALIC_UNDER = re.compile(r"(?<!\w)_(?!\s)([^_\n]+?)(?<!\s)_(?!\w)")
_CODE_SLOT = re.compile(r"\x00(\d+)\x00")
_LINK_DEF = re.compile(r"^\[[^\]\n]+\]:[ \t]+\S")
_FOOTNOTE_DEF = re.compile(r"^\[\^([^\]\n]+)\]:[ \t]*(.*)$")
_FOOTNOTE_REF = re.compile(r"\[\^[^\]\n]+\]")
_INLINE_FOOTNOTE = re.compile(r"\^\[([^\]\n]+)\]")
_ABBREVIATION_DEF = re.compile(r"^\*\[[^\]\n]+\]:")
_CONTAINER_FENCE = re.compile(r"^:{3,}")
_DEFINITION = re.compile(r"^[ \t]{0,3}[:~][ \t]+(\S.*)$")
_THEMATIC = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_ESCAPED = re.compile(r"\\([!-/:-@\[-`{-~])")
_INSERTED = re.compile(r"\+\+([^+\n]+)\+\+")
_MARKED = re.compile(r"==([^=\n]+)==")
_HTML_TAG = re.compile(
    r"<!--.*?-->|</?(?:a|abbr|b|big|br|center|cite|code|del|details|dfn|div|em|font|h[1-6]|hr|i|img"
    r"|ins|kbd|mark|p|picture|q|s|samp|small|source|span|strike|strong|sub|summary|sup|tt|u|var)"
    r"(?:\s[^<>]*)?/?>",
    re.DOTALL | re.IGNORECASE,
)
_HTML_BLOCK = re.compile(r"^<(?:[A-Za-z][\w-]*|/[A-Za-z][\w-]*|!--)(?:[\s/>]|$)")
_ANY_IMAGE = re.compile(f"{_IMAGE.pattern}|{_HTML_IMAGE.pattern}", re.IGNORECASE)
_HTML_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_NUMBERED_TITLE = re.compile(r"^(\d{1,2})\.[ \t]+(\S.*?)\s*$")
_PAGE_FOOTER = re.compile(r"\[Page \d+\]\s*$")
_CODE_SIGNS = re.compile(r"[=;{}<>|]|\S {3,}\S|^[A-Z]+ /\S* HTTP/")
_MIN_REPEATS = 3
_MAX_TITLE = 70
_MAX_TITLE_WORDS = 12
_CONTENTS_PAGE = re.compile(r"\S\s{3,}\d{1,4}$")
_HEADING_ATTRIBUTES = re.compile(r"\s*\{:?\s*[#.][^{}]*\}\s*$")
_BLOCK_FENCE = re.compile(r"^/{3,}(?:\s*[\w-]+)?(?:\s*\|\s*(.*\S))?\s*$")
_ADMONITION = re.compile(r"""^(?:!!!|\?\?\?\+?)\s*[\w-]+(?:\s+["'](.*)["'])?\s*$""")
_GUTENBERG = re.compile(r"^\*{3}\s*(START|END) OF (?:THE|THIS) PROJECT GUTENBERG", re.IGNORECASE)


def extract_text(data: bytes) -> list[Section]:
    """Decode plain text into heading-labeled sections.

    A line repeated at page breaks, such as a running header or a
    ``[Page N]`` footer, is left out, and a paragraph cut by the break is
    joined again. When the body is indented, a short line set flush left
    between blank lines is a title, and so is a ``1. Title`` line standing
    alone. A short line in capitals standing alone is a title too, and so is
    a short ``1. Title`` line standing alone that no list item follows. A
    word hyphenated at the end of a line is joined. A numbered list keeps
    its numbers, counting up from its first. In a Project Gutenberg book,
    only the text between its start and end markers is read.
    """
    return _sections(data, markdown=False)


def extract_markdown(data: bytes) -> list[Section]:
    """Normalize Markdown into heading-labeled sections.

    An image in a sentence stays in that sentence and also becomes its own
    section. A data URI keeps the picture bytes. Inline markup, escapes,
    footnote markers, and inline HTML tags are removed. A block of raw HTML
    is read for its words and pictures. A link definition, an abbreviation
    definition, a thematic break, and a container fence are left out, and so
    is an attribute list such as ``{ #id }`` after a title. A ``///`` block
    or a ``!!!`` admonition keeps its title as text, and the admonition's
    indented body is read as normal text. A footnote keeps its text. A term followed by ``: definition`` lines
    becomes a list. A numbered list keeps its numbers, counting up from its
    first, so a list written ``1. 1. 1.`` reads ``1. 2. 3.``. A table keeps its readable cells. An image in a cell is
    also its own section. A cell that holds a nested table, chart, or canvas
    stays complex, and only that cell is kept.
    """
    return _sections(data, markdown=True)


def _sections(data: bytes, *, markdown: bool) -> list[Section]:
    lines = _decode(data).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    body_indent = 0
    if not markdown:
        lines = _without_page_chrome(_gutenberg_body(lines))
        body_indent = _body_indent(lines)
    sections: list[Section] = []
    state = HeadingState()
    paragraph: list[str] = []
    list_items: list[str] = []
    queued_images: list[tuple[str, bytes | None, str | None]] = []
    table_lines: list[str] = []
    numbering: dict[int, int] = {}
    code: list[str] | None = None
    fence_mark = ""

    def emit_images(images: list[tuple[str, bytes | None, str | None]]) -> None:
        for data, media, media_type in images:
            add_section(sections, "image", data, state, media=media, media_type=media_type)
        images.clear()

    def flush_list() -> None:
        if list_items:
            add_section(sections, "list", "\n".join(list_items), state)
            list_items.clear()
        numbering.clear()
        emit_images(queued_images)

    def list_marker(raw: str, level: int) -> str:
        for deeper in [key for key in numbering if key > level]:
            del numbering[deeper]
        if not raw[0].isdigit():
            numbering.pop(level, None)
            return "-"
        number = numbering.get(level, int(raw[:-1]))
        numbering[level] = number + 1
        return f"{number}."

    def flush_table() -> None:
        if not table_lines:
            return
        raw_lines = list(table_lines)
        table_lines.clear()
        _emit_table(raw_lines, sections, state, markdown=markdown)

    def emit_inline(text: str, *, in_list: bool, level: int = 0, marker: str = "-") -> None:
        body, images, has_words = compose_inline(_pieces(text, markdown=markdown))
        if in_list and has_words and body:
            list_items.append(f"{'  ' * level}{marker} {body}")
            queued_images.extend(images)
            return
        if list_items or queued_images:
            flush_list()
        if has_words and body:
            add_section(sections, "text", body, state)
        emit_images(images)

    def flush_paragraph() -> None:
        if not paragraph:
            return
        text = _join_lines(paragraph)
        paragraph.clear()
        emit_inline(text, in_list=False)

    def previous_blank(cursor: int) -> bool:
        return cursor == 0 or not lines[cursor - 1].strip()

    def add_definition(text: str) -> None:
        body, images, has_words = compose_inline(_pieces(text, markdown=markdown))
        if not has_words or not body:
            return
        term = None
        if paragraph:
            term = _join_lines(paragraph)
            paragraph.clear()
        elif not list_items and sections and sections[-1].kind == "text":
            last = sections[-1]
            if last.headings == state.headings and "\n" not in last.data and len(last.data) <= _MAX_TITLE:
                term = sections.pop().data
        if term is not None:
            label, _images, _words = compose_inline(_pieces(term, markdown=markdown))
            list_items.append(f"- {label}: {body}")
        elif list_items:
            list_items[-1] = f"{list_items[-1]}; {body}"
        else:
            list_items.append(f"- {body}")
        queued_images.extend(images)

    def flush_open() -> None:
        flush_paragraph()
        flush_list()
        flush_table()

    def following_blank(cursor: int) -> bool:
        nxt = cursor + 1
        if nxt >= len(lines):
            return True
        line = lines[nxt]
        if markdown:
            line = _strip_blockquote(line)
        return not line.strip()

    def _apply_heading(level: int, text: str) -> None:
        if markdown:
            text = _HEADING_ATTRIBUTES.sub("", text)
        pieces = _pieces(text, markdown=markdown)
        words = [
            body
            for kind, body, _media, _media_type in pieces
            if kind == "text" and body.strip()
        ]
        images = [
            (body, media, media_type)
            for kind, body, media, media_type in pieces
            if kind == "image" and body
        ]
        state.apply(level, " ".join(words))
        emit_images(images)

    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()

        if code is not None:
            if _is_closing_fence(stripped, fence_mark):
                body = "\n".join(code).strip("\n")
                code = None
                if body:
                    add_section(sections, "code", body, state)
            else:
                code.append(raw.rstrip())
            index += 1
            continue

        if markdown:
            fence = _FENCE.match(stripped)
            if fence is not None:
                flush_open()
                fence_mark = fence.group(1)
                code = []
                index += 1
                continue
            content = _strip_blockquote(raw)
            stripped = content.strip()
        else:
            content = raw

        if markdown:
            footnote = _FOOTNOTE_DEF.match(stripped)
            if footnote is not None:
                flush_open()
                body, index = _read_footnote(lines, index, footnote.group(2))
                emit_inline(f"Footnote {footnote.group(1)}: {body}", in_list=False)
                continue
            if _ABBREVIATION_DEF.match(stripped) or _CONTAINER_FENCE.match(stripped):
                flush_open()
                index += 1
                continue
            block_fence = _BLOCK_FENCE.match(stripped)
            admonition = _ADMONITION.match(stripped)
            if block_fence is not None or admonition is not None:
                flush_open()
                title = (block_fence or admonition).group(1)
                if title:
                    emit_inline(title, in_list=False)
                if admonition is not None:
                    _dedent_block(lines, index + 1)
                index += 1
                continue
            if not paragraph and _HTML_BLOCK.match(stripped):
                flush_open()
                block: list[str] = []
                comment = stripped.startswith("<!--")
                while index < len(lines) and lines[index].strip():
                    block.append(lines[index])
                    index += 1
                    if comment and "-->" in block[-1]:
                        break
                _emit_html_block("\n".join(block), sections, state)
                continue

        if markdown and _LINK_DEF.match(stripped):
            flush_open()
            index += 1
            continue

        if stripped and not _is_table_line(stripped) and index + 1 < len(lines):
            next_line = lines[index + 1]
            if markdown:
                next_line = _strip_blockquote(next_line).strip()
            else:
                next_line = next_line.strip()
            level = _setext_level(next_line, _plain(stripped, markdown=markdown))
            if level is not None:
                flush_open()
                _apply_heading(level, stripped)
                index += 2
                continue

        if not stripped:
            flush_open()
            index += 1
            continue

        if _is_underline(stripped) or _THEMATIC.match(content):
            flush_open()
            index += 1
            continue

        if markdown:
            definition = _DEFINITION.match(content)
            if definition is not None:
                flush_table()
                add_definition(definition.group(1))
                index += 1
                while index < len(lines) and _continues_definition(lines[index]):
                    body, images, _words = compose_inline(_pieces(lines[index].strip(), markdown=True))
                    if body and list_items:
                        list_items[-1] = _join_lines([list_items[-1], body])
                    queued_images.extend(images)
                    index += 1
                continue

        if _is_table_line(stripped):
            flush_paragraph()
            flush_list()
            table_lines.append(stripped)
            index += 1
            continue
        if table_lines:
            flush_table()

        atx = _ATX.match(stripped)
        if atx is not None:
            flush_open()
            _apply_heading(len(atx.group(1)), atx.group(2))
            index += 1
            continue

        outline = _OUTLINE.match(stripped)
        if outline is not None and following_blank(index) and looks_like_heading(outline.group(2)):
            flush_open()
            _apply_heading(min(outline.group(1).count(".") + 1, 6), outline.group(2))
            index += 1
            continue

        if not markdown and _is_plain_title(raw, stripped, body_indent) and previous_blank(index) and following_blank(index):
            flush_open()
            numbered = _NUMBERED_TITLE.match(stripped)
            _apply_heading(1, numbered.group(2) if numbered else stripped)
            index += 1
            continue

        if not markdown and not paragraph and previous_blank(index) and following_blank(index):
            if _is_caps_title(stripped):
                flush_open()
                _apply_heading(1, stripped)
                index += 1
                continue
            numbered = _NUMBERED_TITLE.match(stripped)
            if numbered is not None and _is_numbered_title(numbered.group(2), lines, index):
                flush_open()
                _apply_heading(2, numbered.group(2).rstrip("."))
                index += 1
                continue

        item = _LIST_ITEM.match(content)
        if item is not None:
            flush_paragraph()
            flush_table()
            level = min(len(item.group(1).expandtabs(4)) // 2, 8)
            emit_inline(item.group(3).strip(), in_list=True, level=level, marker=list_marker(item.group(2), level))
            index += 1
            continue
        if list_items and content[:1] in " \t" and stripped:
            body, images, _has_words = compose_inline(_pieces(stripped, markdown=markdown))
            if body:
                list_items[-1] = f"{list_items[-1]} {body}"
            queued_images.extend(images)
            index += 1
            continue
        if list_items:
            flush_list()

        if markdown:
            code_body, next_index = _read_indented_code(lines, index)
        elif not paragraph and previous_blank(index):
            code_body, next_index = _read_plain_code(lines, index, body_indent)
        else:
            code_body, next_index = "", index
        if next_index != index:
            flush_paragraph()
            flush_table()
            if code_body:
                add_section(sections, "code", code_body, state)
            index = next_index
            continue

        paragraph.append(stripped)
        index += 1

    if code:
        body = "\n".join(code).strip("\n")
        if body:
            add_section(sections, "code", body, state)
    flush_open()
    return assign_indexes(sections)


def _gutenberg_body(lines: list[str]) -> list[str]:
    """The book between Project Gutenberg's start and end markers, without its licence."""
    start = end = None
    for index, line in enumerate(lines):
        marker = _GUTENBERG.match(line.strip())
        if marker is None:
            continue
        if marker.group(1).upper() == "START" and start is None:
            start = index
        elif marker.group(1).upper() == "END" and start is not None:
            end = index
            break
    if start is None:
        return lines
    return lines[start + 1 : end]


def _is_caps_title(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    if len(letters) < 3 or any(char.islower() for char in letters):
        return False
    return len(text) <= _MAX_TITLE and looks_like_heading(text)


def _is_numbered_title(title: str, lines: list[str], index: int) -> bool:
    """A short numbered line standing alone heads what follows, unless a list goes on.

    A contents line, with a page number set apart at its end, is not a title.
    """
    if _CONTENTS_PAGE.search(title):
        return False
    title = title.rstrip(".")
    if len(title.split()) > _MAX_TITLE_WORDS or not looks_like_heading(title):
        return False
    for line in lines[index + 1 :]:
        if line.strip():
            return _LIST_ITEM.match(line) is None
    return False


def _dedent_block(lines: list[str], start: int) -> None:
    """Move an admonition's indented body back to the margin, so it reads as text, not code."""
    cursor = start
    while cursor < len(lines):
        line = lines[cursor].expandtabs(4)
        if line.strip() and not line.startswith("    "):
            break
        lines[cursor] = line[4:] if line.strip() else ""
        cursor += 1


def _without_page_chrome(lines: list[str]) -> list[str]:
    """Drop the running header and footer printed at each page break of a paginated text.

    A page break is a form feed or a ``[Page N]`` footer. A line is chrome
    when it is a footer, or when it repeats, with its numbers ignored, on
    either side of three or more breaks. When the paragraph before the break
    ends mid-sentence and the one after goes on in lowercase, the blank lines
    between them are dropped so the paragraph is read as one.
    """
    markers = [index for index, line in enumerate(lines) if "\f" in line or _PAGE_FOOTER.search(line)]
    breaks: list[tuple[int, int]] = []
    for index in markers:
        if breaks and index - breaks[-1][1] <= 3:
            breaks[-1] = (breaks[-1][0], index)
        else:
            breaks.append((index, index))
    if len(breaks) < _MIN_REPEATS:
        return [line.replace("\f", "") for line in lines]
    near: Counter[str] = Counter()
    for first, last in breaks:
        seen: set[str] = set()
        for cursor in range(first - 3, last + 4):
            if 0 <= cursor < len(lines) and lines[cursor].strip():
                seen.add(_chrome_key(lines[cursor]))
        near.update(seen)
    chrome = {key for key, count in near.items() if count >= _MIN_REPEATS}
    kept: list[str] = []
    removed = False
    for line in lines:
        line = line.replace("\f", "")
        if line.strip() and (_PAGE_FOOTER.search(line) or _chrome_key(line) in chrome):
            removed = True
            continue
        if removed and line.strip():
            while kept and not kept[-1].strip():
                kept.pop()
            previous = kept[-1].rstrip() if kept else ""
            if not previous or previous.endswith((".", ":", "!", "?")) or not line.strip()[:1].islower():
                kept.append("")
            removed = False
        kept.append(line)
    return kept


def _chrome_key(line: str) -> str:
    return re.sub(r"\d+", "#", " ".join(line.split()))


def _body_indent(lines: list[str]) -> int:
    """The indent most body lines share, or 0 when most start flush left."""
    counts: Counter[int] = Counter()
    for line in lines:
        if line.strip():
            counts[len(line) - len(line.lstrip(" "))] += 1
    if not counts:
        return 0
    return counts.most_common(1)[0][0]


def _is_plain_title(raw: str, stripped: str, body_indent: int) -> bool:
    """A flush-left short line over an indented body, or a lone ``1. Title`` line."""
    if raw[:1] in " \t" or len(stripped) > _MAX_TITLE or not looks_like_heading(stripped):
        return False
    numbered = _NUMBERED_TITLE.match(stripped)
    if numbered is not None:
        return looks_like_heading(numbered.group(2)) and body_indent >= 2
    return body_indent >= 2 and _LIST_ITEM.match(raw) is None


def _read_plain_code(lines: list[str], index: int, body_indent: int) -> tuple[str, int]:
    """A block set deeper than the body that reads as code, such as a grammar or a request.

    Every line sits at least four columns in from the body, and the block
    holds code symbols or columns aligned with runs of spaces, so an
    indented quotation stays prose.
    """
    end = index
    while end < len(lines) and lines[end].strip():
        end += 1
    block = [line.expandtabs(4) for line in lines[index:end]]
    indents = [len(line) - len(line.lstrip(" ")) for line in block]
    if not block or min(indents) < body_indent + 4:
        return "", index
    if not any(_CODE_SIGNS.search(line.strip()) for line in block):
        return "", index
    shift = min(indents)
    return "\n".join(line[shift:].rstrip() for line in block), end


def _continues_definition(line: str) -> bool:
    """A plain line straight after a definition carries it on, as Markdown allows."""
    stripped = line.strip()
    if not stripped or _DEFINITION.match(line) or _LIST_ITEM.match(line):
        return False
    return not (_ATX.match(stripped) or _FENCE.match(stripped) or _is_table_line(stripped))


def _join_lines(lines: list[str]) -> str:
    """Join wrapped lines, closing up a word hyphenated at a line end."""
    joined = ""
    for line in lines:
        if not joined:
            joined = line
        elif joined.endswith("-") and joined[-2:-1].isalpha() and line[:1].isalnum():
            joined = f"{joined}{line}"
        else:
            joined = f"{joined} {line}"
    return joined


def _read_footnote(lines: list[str], index: int, first: str) -> tuple[str, int]:
    """A footnote's text: its first line and the indented lines that continue it."""
    parts = [first.strip()] if first.strip() else []
    index += 1
    while index < len(lines):
        line = lines[index]
        if line.strip() and line[:1] in " \t":
            parts.append(line.strip())
            index += 1
            continue
        if not line.strip():
            peek = index + 1
            if peek < len(lines) and lines[peek][:1] in " \t" and lines[peek].strip():
                index += 1
                continue
        break
    return _join_lines(parts), index


def _emit_html_block(block: str, sections: list[Section], state: HeadingState) -> None:
    """Read a raw HTML block in Markdown for its title, words, and pictures."""
    soup = BeautifulSoup(block, "html.parser")
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    pictures = []
    for image in soup.find_all("img"):
        link = image.find_parent("a")
        description = (
            image.get("alt") or image.get("title") or (link.get("title") if link else "") or ""
        ).strip()
        pictures.append(render_image(description or None))
        image.decompose()
    heading = soup.find(list(_HTML_HEADINGS))
    text = inline_text(soup) if soup.contents else ""
    if isinstance(heading, Tag) and text and text == inline_text(heading):
        state.apply(_HTML_HEADINGS[heading.name], text)
    elif text:
        add_section(sections, "text", text, state)
    for picture in pictures:
        add_section(sections, "image", picture, state)


def _pieces(
    text: str, *, markdown: bool
) -> list[tuple[str, str, bytes | None, str | None]]:
    if not markdown:
        rendered = render_paragraph(text)
        if rendered:
            return [("text", rendered, None, None)]
        return []

    pieces: list[tuple[str, str, bytes | None, str | None]] = []
    cursor = 0
    for match in _ANY_IMAGE.finditer(text):
        _append_text(pieces, text[cursor : match.start()])
        found = image_from_data_uri(match.group(2))
        media = found[0] if found else None
        media_type = found[1] if found else None
        description = match.group(1) if match.group(1) is not None else match.group(3) or ""
        pieces.append(("image", render_image(_strip_inline(description) or None), media, media_type))
        cursor = match.end()
    _append_text(pieces, text[cursor:])
    return pieces


def _append_text(
    pieces: list[tuple[str, str, bytes | None, str | None]], text: str
) -> None:
    rendered = render_paragraph(_plain(text, markdown=True))
    if rendered:
        pieces.append(("text", rendered, None, None))


def _plain(text: str, *, markdown: bool) -> str:
    if not markdown:
        return text
    return _strip_inline(_LINK.sub(lambda match: match.group(1), text))


def _strip_inline(text: str) -> str:
    protected: list[str] = []

    def hold(match: re.Match[str]) -> str:
        protected.append(match.group(1))
        return f"\x00{len(protected) - 1}\x00"

    def restore(match: re.Match[str]) -> str:
        return protected[int(match.group(1))]

    plain = _INLINE_CODE.sub(hold, text)
    plain = _ESCAPED.sub(hold, plain)
    plain = _HTML_TAG.sub("", plain)
    plain = _FOOTNOTE_REF.sub("", plain)
    plain = _INLINE_FOOTNOTE.sub(r" (\1)", plain)
    plain = _STRIKE.sub(r"\1", plain)
    plain = _INSERTED.sub(r"\1", plain)
    plain = _MARKED.sub(r"\1", plain)
    plain = _BOLD.sub(lambda match: match.group(1) or match.group(2) or "", plain)
    plain = _ITALIC_STAR.sub(r"\1", plain)
    plain = _ITALIC_UNDER.sub(r"\1", plain)
    return _CODE_SLOT.sub(restore, html.unescape(plain))


def _strip_blockquote(line: str) -> str:
    text = line.lstrip(" \t")
    if not text.startswith(">"):
        return line
    while text.startswith(">"):
        text = text[1:]
        if text.startswith(" "):
            text = text[1:]
    return text


def _read_indented_code(lines: list[str], index: int) -> tuple[str, int]:
    if _indented_code_body(_strip_blockquote(lines[index])) is None:
        return "", index
    body: list[str] = []
    while index < len(lines):
        current = _strip_blockquote(lines[index])
        if not current.strip():
            peek = index + 1
            while peek < len(lines) and not _strip_blockquote(lines[peek]).strip():
                peek += 1
            if peek < len(lines) and _indented_code_body(_strip_blockquote(lines[peek])) is not None:
                body.append("")
                index += 1
                continue
            break
        parsed = _indented_code_body(current)
        if parsed is None:
            break
        body.append(parsed)
        index += 1
    return "\n".join(body).strip("\n"), index


def _indented_code_body(line: str) -> str | None:
    expanded = line.expandtabs(4)
    if not expanded.startswith("    ") or not expanded.strip():
        return None
    return expanded[4:].rstrip()


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def _setext_level(underline: str, text: str) -> int | None:
    if not _can_be_setext(underline, text):
        return None
    if _UNDERLINE_H1.match(underline):
        return 1
    if _UNDERLINE_H2.match(underline):
        return 2
    return None


def _can_be_setext(underline: str, text: str) -> bool:
    """A setext title is short, and the underline is at least as wide."""
    cleaned = text.strip()
    mark = underline.strip()
    if len(mark) < len(cleaned):
        return False
    return looks_like_heading(cleaned)


def _is_underline(text: str) -> bool:
    return _UNDERLINE_H1.match(text) is not None or _UNDERLINE_H2.match(text) is not None


def _is_table_line(text: str) -> bool:
    return text.startswith("|") and text.count("|") >= 2


def _is_closing_fence(text: str, marker: str) -> bool:
    return text.startswith(marker) and set(text) <= {marker[0]}


def _emit_table(
    raw_lines: list[str],
    sections: list[Section],
    state: HeadingState,
    *,
    markdown: bool,
) -> None:
    """Keep readable cells, and leave only an unreadable cell complex."""
    rows: list[list[str]] = []
    images: list[tuple[str, bytes | None, str | None]] = []
    complex_cells: list[str] = []
    saw_words = False
    for line in raw_lines:
        cells = _split_row(line)
        if _is_separator(cells):
            continue
        rendered: list[str] = []
        for cell in cells:
            if _CELL_LAYOUT.search(cell):
                rendered.append(render_complex())
                complex_cells.append(cell)
                continue
            label, shown, found = _read_markdown_cell(cell, markdown=markdown)
            if label.strip():
                saw_words = True
            rendered.append(shown)
            images.extend(found)
        rows.append(rendered)
    if complex_cells and not saw_words and not images:
        media_type = "text/markdown" if markdown else "text/plain"
        add_section(
            sections,
            "complex",
            render_complex(),
            state,
            media="\n".join(raw_lines).encode("utf-8"),
            media_type=media_type,
        )
        return
    table = render_table(rows) if saw_words else None
    if table:
        add_section(sections, "table", table, state)
    for data, media, media_type in images:
        add_section(sections, "image", data, state, media=media, media_type=media_type)
    media_type = "text/markdown" if markdown else "text/plain"
    for cell in complex_cells:
        add_section(
            sections,
            "complex",
            render_complex(),
            state,
            media=cell.encode("utf-8"),
            media_type=media_type,
        )


def _read_markdown_cell(
    cell: str, *, markdown: bool
) -> tuple[str, str, list[tuple[str, bytes | None, str | None]]]:
    """Return the cell's words, the text shown in the table, and its images."""
    images: list[tuple[str, bytes | None, str | None]] = []
    if not markdown:
        return cell.strip(), cell.strip(), images
    without_html = _HTML_IMAGE.sub(" ", cell)
    pieces = _pieces(without_html, markdown=True)
    words: list[str] = []
    markers: list[str] = []
    for kind, body, media, media_type in pieces:
        if kind == "image":
            images.append((body, media, media_type))
            markers.append(body)
        elif body.strip():
            words.append(body)
    for match in _HTML_IMAGE.finditer(cell):
        description = render_image((match.group(1) or "").strip())
        images.append((description, None, None))
        markers.append(description)
    label = " ".join(words)
    shown = " ".join(part for part in [label, *markers] if part)
    return label, shown, images


def _split_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_separator(cells: list[str]) -> bool:
    saw_dash = False
    for cell in cells:
        compact = cell.replace(" ", "")
        if not compact:
            continue
        if _SEPARATOR_CELL.fullmatch(compact) is None:
            return False
        saw_dash = True
    return saw_dash
