"""Word documents, converted into sections."""

import re
from io import BytesIO
from xml.etree import ElementTree
from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from ragbytes.extract.docx_numbering import ListNumbering
from ragbytes.extract.render import (
    normalize_inline,
    render_chart,
    render_complex,
    render_image,
    render_paragraph,
    render_table,
)
from ragbytes.extract.sections import (
    HeadingState,
    add_section,
    assign_indexes,
    looks_like_heading,
)
from ragbytes.schemas import Section

_HEADING = re.compile(r"^heading\s+([1-9])$", re.IGNORECASE)
_HEADING_ID = re.compile(r"^heading\s*([1-9])$", re.IGNORECASE)
_TOC = re.compile(r"^toc(?:\s+\d+|\d+)?$", re.IGNORECASE)
_TOC_FIELD = re.compile(r"^\s*TOC\b|PAGEREF\s+_Toc", re.IGNORECASE)
_GENERIC_LABEL = re.compile(r"^(picture|image|chart|graphic)\s*\d*$", re.IGNORECASE)
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
_PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
_WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
_FOOTNOTES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"
_ENDNOTES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/endnotes"
_LAYOUT_PARAGRAPHS = 3
_LAYOUT_WORDS = 60
_TEXT_PIECES = {qn("w:t"): None, qn("w:tab"): "\t", qn("w:br"): "\n", qn("w:cr"): "\n", qn("w:noBreakHyphen"): "-"}
_HIDDEN_TEXT = frozenset({qn("w:txbxContent"), qn("w:moveFrom"), _FALLBACK})
_NOTE_REFERENCES = {qn("w:footnoteReference"): "Footnote", qn("w:endnoteReference"): "Endnote"}


class _Story:
    """What the walk shares across one document: list counters and footnote text."""

    def __init__(self, document: Document) -> None:
        self.numbering = ListNumbering(document)
        self._notes = {
            "Footnote": _note_texts(document, _FOOTNOTES, "w:footnote"),
            "Endnote": _note_texts(document, _ENDNOTES, "w:endnote"),
        }
        self._shown: dict[str, int] = {"Footnote": 0, "Endnote": 0}
        self._seen: set[tuple[str, str]] = set()

    def notes_in(self, element) -> list[str]:
        """Each footnote or endnote this element refers to, as ``Footnote N: text``, numbered in reading order."""
        found: list[str] = []
        for reference in element.iter(*_NOTE_REFERENCES):
            label = _NOTE_REFERENCES[reference.tag]
            note_id = reference.get(qn("w:id")) or ""
            if (label, note_id) in self._seen or _in_fallback(reference):
                continue
            self._seen.add((label, note_id))
            text = self._notes[label].get(note_id)
            if not text:
                continue
            self._shown[label] += 1
            found.append(f"{label} {self._shown[label]}: {text}")
        return found


def extract_docx(data: bytes) -> list[Section]:
    """Convert a Word document into heading-labeled sections.

    A short paragraph that is mostly bold is also a heading when its font is
    larger than the body, or when it keeps the same size and has space above
    it. The largest of those sizes is the top heading, and each smaller size
    is the next level down. A style based on Heading 1 through Heading 9
    keeps that level. Table-of-contents lines are left out, and a drop cap
    joins the paragraph it starts. Text inside content controls and tracked
    insertions is read, and tracked deletions are not. A text box is read
    after the paragraph it is anchored to. A footnote or endnote follows the
    paragraph or table that refers to it, as ``Footnote 1: text``. A numbered
    list item keeps the number Word shows, such as ``1.``, ``a)`` or ``2.1``.
    An embedded picture keeps its original bytes on the image section. A
    one-column table that holds prose is a box around body text, so it is
    read as body text. Any other table keeps its readable cells. A picture
    or a chart in a cell is also its own section. A cell that holds a nested
    layout stays complex, and only that cell's markup is kept.
    """
    try:
        document = Document(BytesIO(data))
    except (PackageNotFoundError, BadZipFile, ValueError) as exc:
        raise ValueError("Could not read the Word document.") from exc
    body_size, heading_levels = _visual_heading_scale(document)
    sections: list[Section] = []
    state = HeadingState()
    _emit_blocks(
        _blocks_in(document.element.body, document),
        document,
        sections,
        state,
        body_size,
        heading_levels,
        _Story(document),
    )
    return assign_indexes(sections)


def _emit_blocks(
    blocks,
    document: Document,
    sections: list[Section],
    state: HeadingState,
    body_size: float,
    heading_levels: dict[float, int],
    story: _Story,
) -> None:
    list_items: list[str] = []
    pending_notes: list[str] = []

    def flush_list() -> None:
        if list_items:
            add_section(sections, "list", "\n".join(list_items), state)
            list_items.clear()
        for note in pending_notes:
            add_section(sections, "text", note, state)
        pending_notes.clear()

    drop_cap = ""
    for block in blocks:
        if isinstance(block, Paragraph):
            if _is_drop_cap(block):
                drop_cap += _paragraph_text(block._element).strip()
                continue
            _append_paragraph(
                block,
                document,
                sections,
                state,
                list_items,
                pending_notes,
                flush_list,
                body_size,
                heading_levels,
                story,
                prefix=drop_cap,
            )
            drop_cap = ""
        elif isinstance(block, Table):
            flush_list()
            if _is_layout_table(block):
                for cell in _distinct_cells(block):
                    _emit_blocks(
                        _blocks_in(cell._tc, cell),
                        document,
                        sections,
                        state,
                        body_size,
                        heading_levels,
                        story,
                    )
            else:
                _emit_table(block, document, sections, state)
                for note in story.notes_in(block._tbl):
                    add_section(sections, "text", note, state)
    flush_list()


def _blocks_in(element, parent):
    """The paragraphs and tables in this container in order, including those inside content controls.

    A content control that holds the table of contents is left out.
    """
    for child in element.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)
        elif child.tag == qn("w:sdt"):
            if _is_contents_control(child):
                continue
            content = child.find(qn("w:sdtContent"))
            if content is not None:
                yield from _blocks_in(content, parent)
        elif child.tag == qn("w:customXml"):
            yield from _blocks_in(child, parent)


def _is_contents_control(sdt) -> bool:
    properties = sdt.find(qn("w:sdtPr"))
    if properties is None:
        return False
    gallery = properties.find(f".//{qn('w:docPartGallery')}")
    return gallery is not None and (gallery.get(qn("w:val")) or "").lower() == "table of contents"


def _paragraph_text(element) -> str:
    """The text a reader sees in this paragraph.

    Runs inside hyperlinks, content controls, and tracked insertions count.
    Deleted and moved-away text does not, and neither does a text box, which
    is read on its own.
    """
    parts: list[str] = []
    for node in element.iter(*_TEXT_PIECES):
        if _hidden_from(node, element):
            continue
        piece = _TEXT_PIECES[node.tag]
        parts.append((node.text or "") if piece is None else piece)
    return "".join(parts)


def _hidden_from(node, element) -> bool:
    parent = node.getparent()
    while parent is not None and parent is not element:
        if parent.tag in _HIDDEN_TEXT:
            return True
        parent = parent.getparent()
    return False


def _text_boxes(element) -> list:
    """Text box contents anchored in this paragraph, once each, without the copy kept for older readers."""
    return [box for box in element.iter(qn("w:txbxContent")) if not _hidden_from(box, element)]


def _cell_paragraphs(cell) -> list[Paragraph]:
    return [block for block in _blocks_in(cell._tc, cell) if isinstance(block, Paragraph)]


def _cell_text(cell) -> str:
    return "\n".join(_paragraph_text(paragraph._element) for paragraph in _cell_paragraphs(cell))


def _note_texts(document: Document, relationship: str, tag: str) -> dict[str, str]:
    """Footnote or endnote text by id, leaving out the separators Word stores beside them."""
    texts: dict[str, str] = {}
    for rel in document.part.rels.values():
        if rel.reltype != relationship or rel.is_external:
            continue
        try:
            root = parse_xml(rel.target_part.blob)
        except (ValueError, SyntaxError):
            continue
        for note in root.iter(qn(tag)):
            if note.get(qn("w:type")) not in {None, "normal"}:
                continue
            text = normalize_inline(" ".join(_paragraph_text(paragraph) for paragraph in note.iter(qn("w:p"))))
            if text:
                texts[note.get(qn("w:id")) or ""] = text
    return texts


def _distinct_cells(table: Table) -> list:
    cells: list = []
    for row in table.rows:
        for cell in row.cells:
            if not any(cell._tc is seen._tc for seen in cells):
                cells.append(cell)
    return cells


def _is_layout_table(table: Table) -> bool:
    """A one-column table holding prose is a box around body text, not data.

    It qualifies when a cell has a heading, several paragraphs, or a long
    passage, so a single-column list of short values stays a table.
    """
    for row in table.rows:
        if len({id(cell._tc) for cell in row.cells}) > 1:
            return False
    for cell in _distinct_cells(table):
        filled = [paragraph for paragraph in _cell_paragraphs(cell) if _paragraph_text(paragraph._element).strip()]
        if len(filled) >= _LAYOUT_PARAGRAPHS:
            return True
        if any(_heading_level(paragraph) is not None for paragraph in filled):
            return True
        if len(_cell_text(cell).split()) >= _LAYOUT_WORDS:
            return True
    return False


def _append_paragraph(
    paragraph,
    document,
    sections,
    state,
    list_items,
    pending_notes,
    flush_list,
    body_size: float,
    heading_levels: dict[float, int],
    story: _Story,
    prefix: str = "",
) -> None:
    if _is_toc(paragraph):
        return
    text = prefix + _paragraph_text(paragraph._element)
    displayed = _displayed_heading_text(paragraph)
    level = _heading_level(paragraph)
    if level is None:
        level = _visual_heading_level(
            paragraph, body_size, heading_levels, _default_size(document)
        )
    notes = story.notes_in(paragraph._element)
    in_list = False
    if level is not None and displayed:
        flush_list()
        state.apply(level, displayed)
    elif list_items and _continues_list(paragraph) and normalize_inline(text):
        rendered = render_paragraph(text)
        if rendered:
            list_items[-1] = f"{list_items[-1]} {rendered}"
            in_list = True
    elif _is_list(paragraph) and normalize_inline(text):
        rendered = render_paragraph(text)
        if rendered:
            depth = _list_level(paragraph)
            marker = story.numbering.marker(_list_id(paragraph), depth)
            list_items.append(f"{'  ' * depth}{marker} {rendered}")
            in_list = True
    elif normalize_inline(text):
        flush_list()
        rendered = render_paragraph(text)
        if rendered:
            add_section(sections, "text", rendered, state)
    else:
        flush_list()
    if in_list:
        pending_notes.extend(notes)
    else:
        for note in notes:
            add_section(sections, "text", note, state)
    visuals = _visuals(paragraph._element, document, state)
    if visuals:
        flush_list()
        sections.extend(visuals)
    for box in _text_boxes(paragraph._element):
        flush_list()
        _emit_blocks(
            _blocks_in(box, paragraph), document, sections, state, body_size, heading_levels, story
        )


def _emit_table(table: Table, document: Document, sections: list[Section], state: HeadingState) -> None:
    """Keep readable cells, and leave only a nested layout complex."""
    rows: list[list[str]] = []
    visuals: list[Section] = []
    complex_cells: list = []
    plain_tables: list[Table] = []
    saw_words = False
    seen_cells: list = []
    for row in table.rows:
        cells: list[str] = []
        previous = None
        for cell in row.cells:
            if cell._tc is previous:
                continue
            previous = cell._tc
            if any(cell._tc is earlier for earlier in seen_cells):
                cells.append("")
                continue
            seen_cells.append(cell._tc)
            if _cell_is_layout(cell):
                cells.append(render_complex())
                complex_cells.append(cell)
                continue
            label = normalize_inline(_cell_text(cell))
            inners = [
                Table(nested, cell)
                for nested in cell._tc.findall(".//" + qn("w:tbl"))
                if _nested_is_plain(nested)
            ]
            plain_tables.extend(inners)
            if inners and not label:
                cells.append("")
                continue
            found: list[Section] = []
            for paragraph in _cell_paragraphs(cell):
                found.extend(_visuals(paragraph._element, document, state))
            if label:
                saw_words = True
            markers = [item.data.split("\n", 1)[0] for item in found]
            cells.append(" ".join(part for part in [label, *markers] if part))
            visuals.extend(found)
        rows.append(cells)
    if complex_cells and not saw_words and not visuals and not plain_tables:
        add_section(
            sections,
            "complex",
            render_complex(),
            state,
            media=table._tbl.xml.encode("utf-8"),
            media_type="application/xml",
        )
        return
    rendered = render_table(rows) if saw_words else None
    if rendered:
        add_section(sections, "table", rendered, state)
    sections.extend(visuals)
    for inner in plain_tables:
        _emit_table(inner, document, sections, state)
    for cell in complex_cells:
        add_section(
            sections,
            "complex",
            render_complex(),
            state,
            media=cell._tc.xml.encode("utf-8"),
            media_type="application/xml",
        )


def _nested_is_plain(nested) -> bool:
    """Return whether this nested table is only text."""
    if nested.find(".//" + qn("w:tbl")) is not None:
        return False
    return not any(_is_visual_drawing(drawing) for drawing in nested.iter(qn("w:drawing")))


def _cell_is_layout(cell) -> bool:
    """Return whether this cell holds a nested table with its own layout."""
    for nested in cell._tc.findall(".//" + qn("w:tbl")):
        if nested.find(".//" + qn("w:tbl")) is not None:
            return True
        if any(_is_visual_drawing(drawing) for drawing in nested.iter(qn("w:drawing"))):
            return True
    return False


def _is_visual_drawing(drawing) -> bool:
    """A picture or chart. A text box is read for its text, so a picture inside one belongs to its paragraphs."""
    if _in_fallback(drawing):
        return False
    graphic_data = drawing.find(f".//{{{_A_NS}}}graphicData")
    uri = graphic_data.get("uri") if graphic_data is not None else ""
    if uri and ("chart" in uri or "picture" in uri):
        return True
    if drawing.find(f".//{qn('w:txbxContent')}") is not None:
        return False
    return drawing.find(f".//{{{_A_NS}}}blip") is not None


def _heading_level(paragraph: Paragraph) -> int | None:
    """Return a heading level from this paragraph or a style it is based on."""
    style = paragraph.style
    seen: set[int] = set()
    while style is not None and id(style) not in seen:
        seen.add(id(style))
        level = _level_from_style(style)
        if level is not None:
            return level
        style = style.base_style
    return _outline_level(paragraph._element)


def _level_from_style(style) -> int | None:
    name = (style.name or "").strip()
    match = _HEADING.match(name)
    if match is not None:
        return int(match.group(1))
    lowered = name.lower()
    if lowered == "title":
        return 1
    if lowered == "subtitle":
        return 2
    style_id = (style.style_id or "").strip()
    id_match = _HEADING.match(style_id) or _HEADING_ID.match(style_id)
    if id_match is not None:
        return int(id_match.group(1))
    if style_id.lower() == "title":
        return 1
    if style_id.lower() == "subtitle":
        return 2
    return _outline_level(style.element)


def _is_toc(paragraph: Paragraph) -> bool:
    """Return whether this paragraph is a table-of-contents line.

    A contents line has a TOC style, links to a ``_Toc`` bookmark, or holds
    the TOC field or a page reference to such a bookmark.
    """
    style = paragraph.style
    seen: set[int] = set()
    while style is not None and id(style) not in seen:
        seen.add(id(style))
        if _TOC.match((style.name or "").strip()) or _TOC.match((style.style_id or "").strip()):
            return True
        style = style.base_style
    element = paragraph._element
    for link in element.iter(qn("w:hyperlink")):
        if (link.get(qn("w:anchor")) or "").startswith("_Toc"):
            return True
    instructions = [node.text or "" for node in element.iter(qn("w:instrText"))]
    instructions += [node.get(qn("w:instr")) or "" for node in element.iter(qn("w:fldSimple"))]
    return any(_TOC_FIELD.search(instruction) for instruction in instructions)


def _is_drop_cap(paragraph: Paragraph) -> bool:
    """A drop cap is a framed paragraph holding the first letters of the next one."""
    properties = paragraph._element.find(qn("w:pPr"))
    if properties is None:
        return False
    frame = properties.find(qn("w:framePr"))
    if frame is None:
        return False
    return (frame.get(qn("w:dropCap")) or "none") in {"drop", "margin"} and bool(
        _paragraph_text(paragraph._element).strip()
    )


def _outline_level(element) -> int | None:
    if element is None:
        return None
    properties = element.find(qn("w:pPr"))
    if properties is None:
        return None
    outline = properties.find(qn("w:outlineLvl"))
    if outline is None:
        return None
    raw = outline.get(qn("w:val"))
    if raw is None or not raw.isdigit():
        return None
    level = int(raw) + 1
    if level > 9:
        return None
    return level


def _visual_heading_scale(document: Document) -> tuple[float, dict[float, int]]:
    """Map each visual heading size to a heading level.

    The most common non-bold size is the body size. A short paragraph that is
    mostly bold qualifies when it is at least half a point larger than the
    body, or the same size with space above it. Sizes are ranked from largest
    to smallest, so a 16pt line is above a 13pt line when the body is 11pt.
    """
    default = _default_size(document)
    body_size = _body_size(document, default)
    found: list[float] = []
    for paragraph in _body_paragraphs(document):
        size = _visual_heading_size(paragraph, body_size, default)
        if size is not None:
            found.append(size)
    ranked = sorted(set(found), reverse=True)
    return body_size, {size: min(index + 1, 9) for index, size in enumerate(ranked)}


def _visual_heading_level(
    paragraph: Paragraph,
    body_size: float,
    heading_levels: dict[float, int],
    default: float | None,
) -> int | None:
    size = _visual_heading_size(paragraph, body_size, default)
    if size is None:
        return None
    return heading_levels.get(size)


def _visual_heading_size(
    paragraph: Paragraph, body_size: float, default: float | None
) -> float | None:
    if body_size <= 0 or _is_toc(paragraph):
        return None
    if not looks_like_heading(_displayed_heading_text(paragraph)):
        return None
    if _is_list(paragraph) and not _oversized_list(paragraph, body_size, default):
        return None
    runs = [run for run in paragraph.runs if run.text.strip()]
    if not runs or _bold_fraction(paragraph) < 0.75:
        return None
    sizes = [_run_size(run, paragraph, default) for run in runs]
    if any(size is None for size in sizes):
        return None
    if max(sizes) - min(sizes) > 1:
        return None
    size = round(max(sizes), 1)
    if size >= body_size + 0.5 or _has_heading_spacing(paragraph):
        return size
    return None


def _oversized_list(paragraph: Paragraph, body_size: float, default: float | None) -> bool:
    """A numbered heading can carry list numbering when the font is clearly larger."""
    sizes = [
        _run_size(run, paragraph, default)
        for run in paragraph.runs
        if run.text.strip()
    ]
    known = [size for size in sizes if size is not None]
    return bool(known) and max(known) >= body_size + 1


def _bold_fraction(paragraph: Paragraph) -> float:
    """Share of letters that are bold. A short unbold run does not block the rest."""
    letters = 0
    bold_letters = 0
    for run in paragraph.runs:
        count = sum(1 for char in run.text if char.isalpha())
        if count == 0:
            continue
        letters += count
        if _run_bold(run, paragraph):
            bold_letters += count
    if letters == 0:
        return 0.0
    return bold_letters / letters


def _has_heading_spacing(paragraph: Paragraph) -> bool:
    """Space above the paragraph, or keep-with-next, marks a same-size title."""
    properties = paragraph._element.find(qn("w:pPr"))
    if properties is None:
        return False
    if properties.find(qn("w:keepNext")) is not None:
        return True
    spacing = properties.find(qn("w:spacing"))
    if spacing is None:
        return False
    before = spacing.get(qn("w:before"))
    return bool(before and before.isdigit() and int(before) >= 120)


def _displayed_heading_text(paragraph: Paragraph) -> str:
    """Return the title as it is shown, including capitals applied as formatting."""
    text = normalize_inline(_paragraph_text(paragraph._element))
    if text and _paragraph_is_caps(paragraph):
        return text.upper()
    return text


def _paragraph_is_caps(paragraph: Paragraph) -> bool:
    saw_letters = False
    for run in paragraph.runs:
        if not any(char.isalpha() for char in run.text):
            continue
        saw_letters = True
        if not _run_caps(run, paragraph):
            return False
    return saw_letters


def _run_caps(run, paragraph: Paragraph) -> bool:
    if _toggle(_run_properties(run._element), "w:caps") or _toggle(
        _run_properties(run._element), "w:smallCaps"
    ):
        return True
    mark = _run_properties(paragraph._element)
    if _toggle(mark, "w:caps") or _toggle(mark, "w:smallCaps"):
        return True
    style = paragraph.style
    seen: set[int] = set()
    while style is not None and id(style) not in seen:
        seen.add(id(style))
        if style.element is not None and (
            _toggle(_run_properties(style.element), "w:caps")
            or _toggle(_run_properties(style.element), "w:smallCaps")
        ):
            return True
        style = style.base_style
    return False


def _run_properties(element):
    if element is None:
        return None
    direct = element.find(qn("w:rPr"))
    if direct is not None:
        return direct
    properties = element.find(qn("w:pPr"))
    if properties is None:
        return None
    return properties.find(qn("w:rPr"))


def _toggle(properties, name: str) -> bool:
    if properties is None:
        return False
    node = properties.find(qn(name))
    if node is None:
        return False
    value = node.get(qn("w:val"))
    if value is None:
        return True
    return value.lower() not in {"0", "false", "off"}


def _body_size(document: Document, default: float | None) -> float:
    sizes: list[float] = []
    for paragraph in _body_paragraphs(document):
        for run in paragraph.runs:
            text = run.text.strip()
            if not text or _run_bold(run, paragraph):
                continue
            size = _run_size(run, paragraph, default)
            if size is not None:
                sizes.extend([size] * len(text))
    if not sizes:
        return default or 0
    sizes.sort()
    return sizes[len(sizes) // 2]


def _default_size(document: Document) -> float | None:
    defaults = document.styles.element.find(qn("w:docDefaults"))
    if defaults is None:
        return None
    size = defaults.find(f".//{qn('w:sz')}")
    raw = size.get(qn("w:val")) if size is not None else None
    if raw is None or not raw.isdigit():
        return None
    return int(raw) / 2


def _run_size(run, paragraph: Paragraph, default: float | None) -> float | None:
    if run.font.size is not None:
        return float(run.font.size.pt)
    styled = _style_font(paragraph, "size")
    if styled is not None:
        return float(styled.pt)
    return default


def _run_bold(run, paragraph: Paragraph) -> bool:
    if run.bold is not None:
        return bool(run.bold)
    styled = _style_font(paragraph, "bold")
    return bool(styled)


def _style_font(paragraph: Paragraph, name: str):
    style = paragraph.style
    seen: set[int] = set()
    while style is not None and id(style) not in seen:
        seen.add(id(style))
        value = getattr(style.font, name, None)
        if value is not None:
            return value
        style = style.base_style
    return None


def _body_paragraphs(document: Document):
    yield from _block_paragraphs(_blocks_in(document.element.body, document))


def _block_paragraphs(blocks):
    for block in blocks:
        if isinstance(block, Paragraph):
            yield block
        elif isinstance(block, Table) and _is_layout_table(block):
            for cell in _distinct_cells(block):
                yield from _block_paragraphs(_blocks_in(cell._tc, cell))


def _is_list(paragraph: Paragraph) -> bool:
    if _continues_list(paragraph):
        return False
    if _style_name(paragraph).lower().startswith("list"):
        return True
    if _numbering(paragraph._element) is not None:
        return True
    return _numbering(_style_element(paragraph)) is not None


def _continues_list(paragraph: Paragraph) -> bool:
    return "list continue" in _style_name(paragraph).lower()


def _list_level(paragraph: Paragraph) -> int:
    for element in (paragraph._element, _style_element(paragraph)):
        numbering = _numbering(element)
        if numbering is None:
            continue
        ilvl = numbering.find(qn("w:ilvl"))
        if ilvl is None:
            continue
        raw = ilvl.get(qn("w:val"))
        if raw is not None and raw.isdigit():
            return min(int(raw), 8)
    return 0


def _list_id(paragraph: Paragraph) -> str | None:
    for element in (paragraph._element, _style_element(paragraph)):
        numbering = _numbering(element)
        if numbering is None:
            continue
        num_id = numbering.find(qn("w:numId"))
        if num_id is not None:
            return num_id.get(qn("w:val"))
    return None


def _style_name(paragraph: Paragraph) -> str:
    if paragraph.style is None or not paragraph.style.name:
        return ""
    return paragraph.style.name


def _style_element(paragraph: Paragraph):
    if paragraph.style is None:
        return None
    return paragraph.style.element


def _numbering(element):
    if element is None:
        return None
    properties = element.find(qn("w:pPr"))
    if properties is None:
        return None
    return properties.find(qn("w:numPr"))


def _visuals(element, document: Document, state: HeadingState) -> list[Section]:
    sections: list[Section] = []
    for drawing in element.iter(qn("w:drawing")):
        if _in_fallback(drawing) or _hidden_from(drawing, element):
            continue
        if not _is_visual_drawing(drawing):
            continue
        graphic_data = drawing.find(f".//{{{_A_NS}}}graphicData")
        uri = graphic_data.get("uri") if graphic_data is not None else ""
        description = _drawing_description(drawing)
        if uri and "chart" in uri:
            chart = drawing.find(f".//{{{_C_NS}}}chart")
            add_section(sections, "chart", _chart_reference(chart, document, description), state)
            continue
        if (uri and "picture" in uri) or drawing.find(f".//{{{_A_NS}}}blip") is not None:
            media, media_type = _picture_bytes(drawing, document)
            add_section(
                sections,
                "image",
                render_image(description),
                state,
                media=media,
                media_type=media_type,
            )
    return sections


def _picture_bytes(drawing, document: Document) -> tuple[bytes | None, str | None]:
    blip = drawing.find(f".//{{{_A_NS}}}blip")
    if blip is None:
        return None, None
    rel_id = blip.get(qn("r:embed"))
    part = document.part.related_parts.get(rel_id) if rel_id else None
    if part is None or not part.blob:
        return None, None
    return part.blob, part.content_type or None


def _chart_reference(chart, document: Document, fallback: str) -> str:
    rel_id = chart.get(qn("r:id")) if chart is not None else None
    part = document.part.related_parts.get(rel_id) if rel_id else None
    if part is None:
        return render_chart(fallback)
    try:
        return _chart_from_xml(part.blob, fallback)
    except ElementTree.ParseError:
        return render_chart(fallback)


def _chart_from_xml(blob: bytes, fallback: str) -> str:
    root = ElementTree.fromstring(blob)
    title = _chart_title(root) or fallback
    return render_chart(title, _chart_rows(root))


def _chart_title(root) -> str:
    title = _first(root, "title")
    if title is None:
        return ""
    parts = [
        normalize_inline(node.text or "")
        for node in title.iter()
        if _local(node.tag) == "t" and node.text
    ]
    return " ".join(part for part in parts if part)


def _chart_rows(root) -> list[list[str]]:
    series = [node for node in root.iter() if _local(node.tag) == "ser"]
    if not series:
        return []

    columns: list[tuple[str, dict[int, str]]] = []
    categories: dict[int, str] = {}
    for index, item in enumerate(series, start=1):
        name = _series_name(item, index)
        cats = _points(_first(item, "cat"))
        values = _points(_first(item, "val"))
        if cats and not categories:
            categories = cats
        if values:
            columns.append((name, values))
    if not columns:
        return []

    indexes = set(categories)
    for _, values in columns:
        indexes.update(values)
    if not indexes:
        return []

    header = (["Category"] if categories else []) + [name for name, _ in columns]
    rows = [header]
    for index in sorted(indexes):
        row = [categories.get(index, "")] if categories else []
        row.extend(values.get(index, "") for _, values in columns)
        rows.append(row)
    return rows


def _series_name(series, index: int) -> str:
    title = _first(series, "tx")
    if title is None:
        return f"Series {index}"
    values = [
        normalize_inline(node.text or "")
        for node in title.iter()
        if _local(node.tag) == "v" and node.text
    ]
    if not any(values):
        values = [
            normalize_inline(node.text or "")
            for node in title.iter()
            if _local(node.tag) == "t" and node.text
        ]
    name = " ".join(value for value in values if value)
    return name or f"Series {index}"


def _points(container) -> dict[int, str]:
    found: dict[int, str] = {}
    if container is None:
        return found
    for point in container.iter():
        if _local(point.tag) != "pt":
            continue
        raw = point.get("idx")
        try:
            index = int(raw) if raw is not None else len(found)
        except ValueError:
            index = len(found)
        value = ""
        for child in list(point):
            if _local(child.tag) == "v" and child.text:
                value = normalize_inline(child.text)
                break
        found[index] = value
    return found


def _drawing_description(drawing) -> str:
    for tag in (f"{{{_WP_NS}}}docPr", f"{{{_PIC_NS}}}cNvPr"):
        node = drawing.find(f".//{tag}")
        if node is None:
            continue
        for attribute in ("descr", "title"):
            text = normalize_inline(node.get(attribute))
            if text and _GENERIC_LABEL.match(text) is None:
                return text
    return ""


def _in_fallback(element) -> bool:
    parent = element.getparent()
    while parent is not None:
        if parent.tag == _FALLBACK:
            return True
        parent = parent.getparent()
    return False


def _first(element, name: str):
    for node in element.iter():
        if node is not element and _local(node.tag) == name:
            return node
    return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
