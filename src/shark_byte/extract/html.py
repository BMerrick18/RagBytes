"""HTML documents, converted into sections."""

import re

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from shark_byte.extract.render import (
    render_chart,
    render_complex,
    render_image,
    render_paragraph,
    render_table,
)
from shark_byte.extract.sections import (
    HeadingState,
    add_section,
    assign_indexes,
    compose_inline,
    image_from_data_uri,
    looks_like_heading,
)
from shark_byte.schemas import Section, SectionKind

_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_MSO_HEADING = re.compile(r"msoheading([1-6])")
_NOT_A_HEADING_HOST = {"table", "ul", "ol", "dl", "figure", "pre", "img", "svg", "canvas", "li"}
_PARAGRAPHS = {"p", "blockquote", "figcaption", "dt", "dd"}
_BLOCKS = _PARAGRAPHS | set(_HEADINGS) | {
    "address",
    "article",
    "aside",
    "div",
    "dl",
    "fieldset",
    "figure",
    "footer",
    "form",
    "header",
    "li",
    "main",
    "nav",
    "ol",
    "pre",
    "section",
    "table",
    "ul",
}
_Piece = tuple[SectionKind, str, bytes | None, str | None]
_CHART_WORD = re.compile(r"\b(?:charts?|graphs?)\b")
_CHROME_ROLES = frozenset({"navigation", "search", "contentinfo"})
_SECTIONING = ["article", "section", "aside", "blockquote"]
_MIN_LANGUAGE_LINKS = 5
_BOILERPLATE = ", ".join(
    [
        "sup.reference",
        "sup.noprint",
        ".mw-editsection",
        ".mw-jump-link",
        ".mw-indicators",
        ".mw-cite-backlink",
        ".headerlink",
        ".wb-langlinks-edit",
        ".noprint",
        ".printfooter",
        ".navbox",
        ".hatnote",
        ".reflist",
        ".mw-references-wrap",
        "#catlinks",
        "#siteSub",
        "#contentSub",
        "#toc",
        ".toc",
    ]
)
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)
_MAX_SPAN = 20
_SPAN_REPEAT_LIMIT = 40
_LAYOUT_WORDS = 150
_LAYOUT_BLOCKS = ["h1", "h2", "h3", "h4", "h5", "h6", "pre", "p"]


def extract_html(data: bytes) -> list[Section]:
    """Convert HTML into heading-labeled sections.

    An image becomes its own section. A data URI keeps the picture bytes.
    Comments are left out. An ordered list keeps its numbers. A table keeps
    its readable rows. An image or a
    chart in a cell is also its own section. A table that lays out the page,
    with headings, code, or long passages in a cell, is read as page content,
    leaving out a cell that is mostly links. Otherwise, a cell that is itself
    a nested layout stays complex, and only that cell's markup is kept. A figure is
    read the same way: each picture or chart is emitted, and a nested layout
    is the part left complex.

    Page chrome is left out. When the page marks one main region, only that
    region is read. Navigation, search boxes, the page footer, and a list of
    links to the same page in other languages are skipped. So are citation
    markers, reference lists, edit links, contents boxes, notes about other
    pages, and anything styled as hidden, as wikis and CMS pages print them.
    """
    soup = BeautifulSoup(data, "html.parser")
    for tag in soup.find_all(["script", "style", "noscript", "template"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for menu in _language_menus(soup):
        menu.decompose()
    for tag in [*soup.select(_BOILERPLATE), *soup.find_all(style=_HIDDEN_STYLE)]:
        if not tag.decomposed:
            tag.decompose()

    sections: list[Section] = []
    root = _main_region(soup)
    state = HeadingState()
    title = _title_outside(root, soup)
    if title:
        state.apply(1, title)
    if isinstance(root, Tag):
        _walk(root, sections, state)
    return assign_indexes(sections)


def _main_region(soup: BeautifulSoup) -> Tag | BeautifulSoup:
    mains = soup.find_all("main") or soup.find_all(attrs={"role": "main"})
    if len(mains) == 1:
        return mains[0]
    return soup.body if soup.body is not None else soup


def _title_outside(root: Tag | BeautifulSoup, soup: BeautifulSoup) -> str:
    """The page's one top heading, when it sits outside the main region."""
    if root.name != "main" and root.get("role") != "main":
        return ""
    if root.find("h1") is not None:
        return ""
    titles = soup.find_all("h1")
    if len(titles) != 1:
        return ""
    return inline_text(titles[0])


def _language_menus(soup: BeautifulSoup) -> list[Tag]:
    """Lists whose links are mostly the same page in other languages."""
    menus: list[Tag] = []
    for menu in soup.find_all(["ul", "ol"]):
        links = menu.find_all("a")
        alternates = sum(1 for link in links if link.get("hreflang"))
        if alternates >= _MIN_LANGUAGE_LINKS and alternates * 5 >= len(links) * 4:
            menus.append(menu)
    return [menu for menu in menus if not any(_inside(menu, other) for other in menus)]


def _is_page_chrome(node: Tag) -> bool:
    name = node.name
    if name in {"nav", "search"} or node.get("role") in _CHROME_ROLES:
        return True
    return name == "footer" and node.find_parent(_SECTIONING) is None


def _walk(node: Tag, sections: list[Section], state: HeadingState) -> None:
    name = node.name
    if name in {"hr", "br"} or _is_page_chrome(node):
        return
    if node.has_attr("hidden"):
        return
    if node.get("aria-hidden") == "true" and not _looks_like_chart(node):
        return
    if name in _HEADINGS:
        state.apply(_HEADINGS[name], inline_text(node))
        _heading_media(node, sections, state)
        return
    level = _markup_heading_level(node)
    if level is not None and not _contains_block(node):
        state.apply(level, inline_text(node))
        _heading_media(node, sections, state)
        return
    if name == "dl":
        _definition_list(node, sections, state)
        return
    if name == "table":
        if _is_layout_table(node):
            for cell in _own_cells(node):
                if not _is_link_menu(cell):
                    _walk_children(cell, sections, state)
        else:
            _emit_table(node, sections, state)
        return
    if name == "figure":
        _figure(node, sections, state)
        return
    if name in {"ul", "ol"}:
        _list(node, sections, state)
        return
    if name == "li":
        _list_item(node, sections, state)
        return
    if name == "pre":
        text = "\n".join(line.rstrip() for line in node.get_text().strip("\n").splitlines())
        if text.strip():
            add_section(sections, "code", text, state)
        return
    if name == "img":
        if not _is_tiny(node):
            media, media_type = _image_media(node)
            add_section(
                sections,
                "image",
                render_image(_image_description(node)),
                state,
                media=media,
                media_type=media_type,
            )
        return
    if name in {"svg", "canvas"}:
        _emit_visual(node, sections, state)
        return
    if name in _PARAGRAPHS and not _contains_block(node):
        _emit_inline(node, sections, state)
        return
    if _contains_block(node):
        _walk_children(node, sections, state)
        return
    _emit_inline(node, sections, state)


def _walk_children(node: Tag, sections: list[Section], state: HeadingState) -> None:
    for child in node.children:
        if isinstance(child, Tag):
            _walk(child, sections, state)
        elif type(child) is NavigableString:
            rendered = render_paragraph(str(child))
            if rendered:
                add_section(sections, "text", rendered, state)


def _list(node: Tag, sections: list[Section], state: HeadingState) -> None:
    items, images, flush_items = _list_buffer(sections, state)
    _append_list(node, items, images, 0, flush_items, sections, state)
    flush_items()


def _list_item(node: Tag, sections: list[Section], state: HeadingState) -> None:
    items, images, flush_items = _list_buffer(sections, state)
    _append_list_item(node, "-", items, images, 0, flush_items, sections, state)
    flush_items()


def _append_list(
    node: Tag,
    items: list[str],
    images: list[tuple[str, bytes | None, str | None]],
    depth: int,
    flush_items,
    sections: list[Section],
    state: HeadingState,
) -> None:
    """Add a list's items. An ordered list numbers them from ``start``, and an item's ``value`` resets the count."""
    number = _integer(node.get("start"), 1)
    for item in node.find_all("li", recursive=False):
        marker = "-"
        if node.name == "ol":
            number = _integer(item.get("value"), number)
            marker = f"{number}."
            number += 1
        _append_list_item(item, marker, items, images, depth, flush_items, sections, state)


def _integer(raw, default: int) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _list_buffer(sections: list[Section], state: HeadingState):
    items: list[str] = []
    images: list[tuple[str, bytes | None, str | None]] = []

    def flush_items() -> None:
        if items:
            add_section(sections, "list", "\n".join(items), state)
            items.clear()
        _emit_images(images, sections, state)

    return items, images, flush_items


def _append_list_item(
    item: Tag,
    marker: str,
    items: list[str],
    images: list[tuple[str, bytes | None, str | None]],
    depth: int,
    flush_items,
    sections: list[Section],
    state: HeadingState,
) -> None:
    text, pics, has_words = compose_inline(_pieces(item))
    if has_words and text:
        items.append(f"{'  ' * depth}{marker} {text}")
        images.extend(pics)
    elif pics:
        flush_items()
        _emit_images(pics, sections, state)
    for child in item.find_all(["ul", "ol"], recursive=False):
        _append_list(child, items, images, depth + 1, flush_items, sections, state)
    for table in item.find_all("table"):
        if table.find_parent("li") is not item or table.find_parent("table") is not None:
            continue
        flush_items()
        _emit_table(table, sections, state)


def _emit_inline(node: Tag, sections: list[Section], state: HeadingState) -> None:
    text, images, has_words = compose_inline(_pieces(node))
    if has_words and text:
        add_section(sections, "text", text, state)
    _emit_images(images, sections, state)


def _emit_images(
    images: list[tuple[str, bytes | None, str | None]],
    sections: list[Section],
    state: HeadingState,
) -> None:
    for data, media, media_type in images:
        add_section(sections, "image", data, state, media=media, media_type=media_type)
    images.clear()


def _pieces(node: Tag) -> list[_Piece]:
    pieces: list[_Piece] = []
    texts: list[str] = []

    def flush_text() -> None:
        rendered = render_paragraph("".join(texts))
        texts.clear()
        if rendered:
            pieces.append(("text", rendered, None, None))

    def visit(current: Tag) -> None:
        for child in current.children:
            if type(child) is NavigableString:
                texts.append(str(child))
                continue
            if not isinstance(child, Tag):
                continue
            if child.name in {"ul", "ol", "table"}:
                continue
            if child.name == "br":
                texts.append(" ")
                continue
            if child.name == "img":
                if not _is_tiny(child):
                    flush_text()
                    media, media_type = _image_media(child)
                    pieces.append(
                        ("image", render_image(_image_description(child)), media, media_type)
                    )
                continue
            if child.name in {"svg", "canvas"}:
                visual = _visual(child)
                if visual is not None:
                    flush_text()
                    pieces.append((visual[0], visual[1], None, None))
                continue
            visit(child)

    visit(node)
    flush_text()
    return pieces


def _emit_table(node: Tag, sections: list[Section], state: HeadingState) -> None:
    """Emit readable rows, and leave only an unreadable cell complex.

    The table's caption is written on the line above it. Plain text stays in the table. An image or a chart in a cell is written
    into that cell and also becomes its own section. A nested table of plain
    cells is emitted as its own table. A cell that holds a nested layout is
    the complex region, not the surrounding table.
    """
    rows: list[list[str]] = []
    visuals: list[Section] = []
    nested_tables: list[Tag] = []
    complex_cells: list[Tag] = []
    saw_words = False
    carried: dict[int, tuple[str, int]] = {}
    for row in node.find_all("tr"):
        if row.find_parent("table") is not node:
            continue
        spans: list[tuple[str, int, int]] = []
        for cell in row.find_all(["th", "td"], recursive=False):
            if not isinstance(cell, Tag):
                continue
            if _cell_is_layout(cell, node):
                spans.append((render_complex(), 1, 1))
                complex_cells.append(cell)
                continue
            label, found, inners = _read_cell(cell, node, state, visuals)
            if label.strip():
                saw_words = True
            spans.append((found, _span(cell.get("colspan")), _span(cell.get("rowspan"))))
            nested_tables.extend(inners)
        cells = _lay_out_row(spans, carried)
        if any(cell.strip() for cell in cells):
            rows.append(cells)
    if complex_cells and not saw_words and not visuals and not nested_tables:
        _emit_complex(node, sections, state)
        return
    caption_node = node.find("caption", recursive=False)
    caption = inline_text(caption_node) if isinstance(caption_node, Tag) else ""
    rendered = render_table(rows) if saw_words else None
    if rendered:
        add_section(sections, "table", f"{caption}\n{rendered}" if caption else rendered, state)
    elif caption:
        add_section(sections, "text", caption, state)
    sections.extend(visuals)
    for inner in nested_tables:
        _emit_table(inner, sections, state)
    for cell in complex_cells:
        _emit_complex(cell, sections, state)


def _own_cells(table: Tag) -> list[Tag]:
    return [
        cell
        for cell in table.find_all(["td", "th"])
        if isinstance(cell, Tag) and cell.find_parent("table") is table
    ]


def _is_layout_table(table: Tag) -> bool:
    """A table used to place the page's content rather than to hold data.

    One of its own cells has a heading or a code block, or a long passage
    split into several paragraphs.
    """
    for cell in _own_cells(table):
        owned = [
            tag
            for tag in cell.find_all(_LAYOUT_BLOCKS)
            if isinstance(tag, Tag) and tag.find_parent("table") is table
        ]
        if any(tag.name in _HEADINGS or tag.name == "pre" for tag in owned):
            return True
        paragraphs = [tag for tag in owned if tag.name == "p"]
        if len(paragraphs) >= 2 and len(_cell_words(cell).split()) >= _LAYOUT_WORDS:
            return True
    return False


def _is_link_menu(cell: Tag) -> bool:
    """A cell that is mostly links, such as a sidebar beside the content."""
    words = len(inline_text(cell).split())
    if words == 0 or words >= _LAYOUT_WORDS:
        return False
    linked = sum(len(inline_text(link).split()) for link in cell.find_all("a"))
    return linked * 2 >= words


def _lay_out_row(spans: list[tuple[str, int, int]], carried: dict[int, tuple[str, int]]) -> list[str]:
    """Place a row's cells on the table grid.

    A short label spanning columns, such as a header over two columns,
    repeats in each of them, and a cell spanning rows repeats in the rows
    below, so every row reads as a whole record. Longer text spanning columns
    is written once, in its first column. A row that is one cell across the
    table, such as a group title, is written once. ``carried`` holds the
    cells still reaching down from rows above.
    """
    cells: list[str] = []
    pending = list(spans)
    alone = len(spans) == 1
    column = 0
    while pending or any(index >= column for index in carried):
        if column in carried:
            text, remaining = carried[column]
            cells.append(text)
            if remaining > 1:
                carried[column] = (text, remaining - 1)
            else:
                del carried[column]
            column += 1
            continue
        if not pending:
            cells.append("")
            column += 1
            continue
        text, width, height = pending.pop(0)
        repeat = not alone and len(text) <= _SPAN_REPEAT_LIMIT
        for offset in range(width):
            shown = text if offset == 0 or repeat else ""
            cells.append(shown)
            if height > 1:
                carried[column + offset] = (shown, height - 1)
        column += width
    return cells


def _span(raw) -> int:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return 1
    return min(max(value, 1), _MAX_SPAN)


def _cell_is_layout(cell: Tag, outer: Tag) -> bool:
    """Return whether this cell is a nested layout rather than a data cell."""
    nested = _nested_tables(cell, outer)
    visuals = _owned_visuals(cell, outer)
    if len(nested) > 1 or (nested and visuals):
        return True
    for table in nested:
        if _nested_tables(table, table) or _owned_visuals(table, table):
            return True
    return False


def _read_cell(
    cell: Tag,
    outer: Tag,
    state: HeadingState,
    visuals: list[Section],
) -> tuple[str, str, list[Tag]]:
    """Return the cell's own words, its table text, and any plain inner tables."""
    nested = _nested_tables(cell, outer)
    tags = _owned_visuals(cell, outer)
    label = _cell_words(cell)
    markers: list[str] = []
    for tag in tags:
        if tag.name == "img":
            description = render_image(_image_description(tag))
            media, media_type = _image_media(tag)
            add_section(
                visuals,
                "image",
                description,
                state,
                media=media,
                media_type=media_type,
            )
            markers.append(description)
            continue
        visual = _visual(tag)
        if visual is None:
            continue
        add_section(visuals, visual[0], visual[1], state)
        markers.append(visual[1].split("\n", 1)[0])
    shown = " ".join(part for part in [label, *markers] if part)
    return label, shown, nested


def _cell_words(cell: Tag) -> str:
    """Return the text that belongs to this cell, not to a nested region."""
    return inline_text(cell, skip=frozenset({"table", "img", "svg", "canvas"}))


def inline_text(node: Tag, skip: frozenset[str] = frozenset()) -> str:
    """The node's words as one line, spaced the way a browser shows them.

    Inline tags such as links and bold add no space, so ``<b>word</b>,``
    stays ``word,``. A line break or a block element inside separates words.
    """
    parts: list[str] = []

    def visit(current: Tag) -> None:
        for child in current.children:
            if type(child) is NavigableString:
                parts.append(str(child))
                continue
            if not isinstance(child, Tag) or child.name in skip:
                continue
            if child.name == "br":
                parts.append(" ")
                continue
            block = child.name in _BLOCKS or child.name in {"td", "th", "tr"}
            if block:
                parts.append(" ")
            visit(child)
            if block:
                parts.append(" ")

    visit(node)
    return render_paragraph("".join(parts)) or ""


def _nested_tables(scope: Tag, outer: Tag) -> list[Tag]:
    return [
        table
        for table in scope.find_all("table")
        if isinstance(table, Tag) and table.find_parent("table") is outer
    ]


def _owned_visuals(scope: Tag, outer: Tag) -> list[Tag]:
    found: list[Tag] = []
    for tag in scope.find_all(["img", "svg", "canvas"]):
        if not isinstance(tag, Tag) or tag.find_parent("table") is not outer:
            continue
        if tag.name == "img" and _is_tiny(tag):
            continue
        if tag.name in {"svg", "canvas"} and _is_decorative(tag):
            continue
        found.append(tag)
    return found


def _emit_complex(node: Tag, sections: list[Section], state: HeadingState) -> None:
    add_section(
        sections,
        "complex",
        render_complex(),
        state,
        media=str(node).encode("utf-8"),
        media_type="text/html",
    )


def _figure(node: Tag, sections: list[Section], state: HeadingState) -> None:
    caption_node = node.find("figcaption")
    caption = ""
    if isinstance(caption_node, Tag):
        caption = inline_text(caption_node)
    caption_tag = caption_node if isinstance(caption_node, Tag) else None
    visuals = [
        child
        for child in node.find_all(["img", "svg", "canvas"])
        if caption_tag is None or not _inside(child, caption_tag)
    ]
    caption_used = False
    emitted = False
    for visual in visuals:
        use_caption = caption if caption and not caption_used else ""
        if visual.name == "img":
            if _is_tiny(visual):
                continue
            media, media_type = _image_media(visual)
            add_section(
                sections,
                "image",
                render_image(use_caption or _image_description(visual)),
                state,
                media=media,
                media_type=media_type,
            )
            caption_used = True
            emitted = True
            continue
        embedded = _visual(visual, use_caption)
        if embedded is None:
            continue
        add_section(sections, embedded[0], embedded[1], state)
        caption_used = True
        emitted = True
    if not emitted and caption:
        rendered = render_paragraph(caption)
        if rendered:
            add_section(sections, "text", rendered, state)
    for visual in visuals:
        visual.decompose()
    if caption_tag is not None:
        caption_tag.decompose()
    _walk_children(node, sections, state)


def _markup_heading_level(node: Tag) -> int | None:
    """Return a heading level from role, Word HTML classes, or a bold title line."""
    if node.name in _NOT_A_HEADING_HOST:
        return None
    text = inline_text(node)
    if not text or len(text) > 200:
        return None
    role = str(node.get("role") or "").lower()
    if role == "heading":
        return _aria_level(node.get("aria-level"))
    classes = _class_text(node)
    compact = re.sub(r"[^a-z0-9]+", "", classes)
    mso = _MSO_HEADING.search(compact)
    if mso is not None:
        return int(mso.group(1))
    if "msotitle" in compact:
        return 1
    if "msosubtitle" in compact:
        return 2
    tokens = set(re.split(r"[^a-z0-9]+", classes))
    if looks_like_heading(text):
        if "subtitle" in tokens or "subheading" in tokens or {"section", "title"} <= tokens:
            return 2
        if "title" in tokens or "heading" in tokens:
            return 1
        if node.name == "p":
            return _bold_paragraph_level(node, text)
    return None


def _aria_level(raw) -> int:
    try:
        level = int(str(raw))
    except (TypeError, ValueError):
        return 2
    return min(max(level, 1), 6)


def _class_text(node: Tag) -> str:
    classes = node.get("class") or []
    if isinstance(classes, str):
        return classes.lower()
    return " ".join(str(name) for name in classes).lower()


def _bold_paragraph_level(node: Tag, text: str) -> int | None:
    if not looks_like_heading(text):
        return None
    sized = _declared_size_level(node.get("style"))
    weight = _font_weight(node.get("style"))
    if _bold_fraction(node) >= 0.75 or (weight is not None and weight >= 600):
        return sized or 2
    return sized


def _bold_fraction(node: Tag) -> float:
    letters = 0
    bold_letters = 0

    def visit(tag: Tag, inherited: bool) -> None:
        nonlocal letters, bold_letters
        weight = _font_weight(tag.get("style"))
        current = inherited if weight is None else weight >= 600
        if tag.name in {"b", "strong"}:
            current = True
        for child in tag.children:
            if type(child) is NavigableString:
                count = sum(char.isalpha() for char in str(child))
                letters += count
                if current:
                    bold_letters += count
            elif isinstance(child, Tag):
                visit(child, current)

    visit(node, False)
    if letters == 0:
        return 0.0
    return bold_letters / letters


def _font_weight(style: str | None) -> int | None:
    if not style:
        return None
    match = re.search(r"font-weight\s*:\s*([a-z0-9]+)", str(style), re.IGNORECASE)
    if match is None:
        return None
    raw = match.group(1).lower()
    if raw == "bold":
        return 700
    if raw in {"normal", "lighter"}:
        return 400
    if raw.isdigit():
        return int(raw)
    return None


def _declared_size_level(style: str | None) -> int | None:
    """A clearly larger font size is a top heading. Other sizes stay undecided."""
    if not style:
        return None
    match = re.search(
        r"font-size\s*:\s*([0-9.]+)\s*(px|em|rem|%)?",
        str(style),
        re.IGNORECASE,
    )
    if match is None:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    unit = (match.group(2) or "px").lower()
    if unit == "px" and value >= 20:
        return 1
    if unit in {"em", "rem"} and value >= 1.4:
        return 1
    if unit == "%" and value >= 140:
        return 1
    return None


def _heading_media(node: Tag, sections: list[Section], state: HeadingState) -> None:
    for child in node.find_all(["img", "svg", "canvas"]):
        if child.name == "img":
            if _is_tiny(child):
                continue
            media, media_type = _image_media(child)
            add_section(
                sections,
                "image",
                render_image(_image_description(child)),
                state,
                media=media,
                media_type=media_type,
            )
            continue
        _emit_visual(child, sections, state)


def _definition_list(node: Tag, sections: list[Section], state: HeadingState) -> None:
    """A list of terms and their definitions.

    A list with no terms only indents its entries, as wikis do for quotes and
    replies, so each entry is read as its own paragraph.
    """
    entries = node.find_all(["dt", "dd"], recursive=False)
    if entries and not any(entry.name == "dt" for entry in entries):
        for entry in entries:
            _walk(entry, sections, state)
        return
    items: list[str] = []
    term: str | None = None
    definitions: list[str] = []

    def flush() -> None:
        nonlocal term
        if term and definitions:
            items.append(f"- {term}: {' '.join(definitions)}")
        elif term:
            items.append(f"- {term}")
        else:
            items.extend(f"- {definition}" for definition in definitions)
        term = None
        definitions.clear()

    for child in entries:
        text = inline_text(child)
        if child.name == "dt":
            flush()
            term = text or None
            continue
        if text:
            definitions.append(text)
    flush()
    if items:
        add_section(sections, "list", "\n".join(items), state)
    for image in node.find_all("img"):
        if _is_tiny(image):
            continue
        media, media_type = _image_media(image)
        add_section(
            sections,
            "image",
            render_image(_image_description(image)),
            state,
            media=media,
            media_type=media_type,
        )


def _emit_visual(tag: Tag, sections: list[Section], state: HeadingState) -> None:
    visual = _visual(tag)
    if visual is not None:
        add_section(sections, visual[0], visual[1], state)


def _inside(node: Tag, ancestor: Tag) -> bool:
    parent = node.parent
    while isinstance(parent, Tag):
        if parent is ancestor:
            return True
        parent = parent.parent
    return False


def _visual(tag: Tag, caption: str = "") -> tuple[SectionKind, str] | None:
    if _is_decorative(tag):
        return None
    description = caption or _visual_description(tag)
    if tag.name == "canvas" or _looks_like_chart(tag):
        return "chart", render_chart(description)
    return "image", render_image(description)


def _image_media(tag: Tag) -> tuple[bytes | None, str | None]:
    found = image_from_data_uri(str(tag.get("src") or ""))
    if found is None:
        return None, None
    return found


def _image_description(tag: Tag) -> str:
    return tag.get("alt") or tag.get("title") or ""


def _visual_description(tag: Tag) -> str:
    labelled = tag.get("aria-label") or tag.get("title")
    if labelled:
        return str(labelled)
    title = tag.find("title")
    if isinstance(title, Tag):
        return title.get_text(" ", strip=True)
    return ""


def _looks_like_chart(tag: Tag) -> bool:
    classes = " ".join(tag.get("class") or [])
    blob = " ".join(
        [classes, str(tag.get("id") or ""), str(tag.get("role") or ""), str(tag.get("aria-label") or "")]
    ).lower()
    return _CHART_WORD.search(blob) is not None


def _is_decorative(tag: Tag) -> bool:
    if _is_tiny(tag):
        return True
    if tag.name != "svg" or _looks_like_chart(tag) or _visual_description(tag):
        return False
    classes = " ".join(tag.get("class") or []).lower()
    return "icon" in classes or tag.get("aria-hidden") == "true"


def _is_tiny(tag: Tag) -> bool:
    width = _length(tag.get("width"))
    height = _length(tag.get("height"))
    if width is None or height is None:
        return False
    return width < 24 and height < 24


def _length(value: str | None) -> float | None:
    if not value:
        return None
    digits = "".join(character for character in value if character.isdigit() or character == ".")
    if not digits:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def _contains_block(node: Tag) -> bool:
    return any(child.name in _BLOCKS for child in node.find_all(True, recursive=False))
