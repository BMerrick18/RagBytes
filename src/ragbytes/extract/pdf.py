"""PDFs, converted into sections.

Each page is read on its own. A page split by a wide empty band, such as
several slides printed on one sheet, is read one band at a time. One column
is read top to bottom. A clear gap between columns is read one column at a
time, left to right, and a line that crosses the gap stays where it sits.
Words are spaced by the gap between them, not by how the PDF splits them,
and a word is placed on its line by its baseline, since some maths fonts
report glyph boxes far from where the glyph is set. Text painted under a
later image, or under a later copy of itself, is hidden and left out, and
so is text that falls wholly outside its clipping path. Text on an embedded image is left out of the text,
except on a wide backdrop image behind a title or banner. A page with no
text and one image covering most of it is a scan, kept whole as a picture.
An embedded image is cropped from the page and kept as PNG bytes. A
diagram or chart drawn as vectors is kept as a picture of its region with
its words as the description. A short caption under the image, or a
``Figure N`` caption above or below it, is kept on the image. A hyphen at
the end of a visual line is kept when the next line continues the word.

A table is a run of ruled rows whose text sits in two or more columns. A
frame around the page, a rule under a title, or a box beside a paragraph
also draw edges, but a row with one wide cell is prose and stays in the text
flow. An edge that slices through words is not a column. Each cell is read
from the words inside it, a word set across a kept column edge is split at
that edge, and a column that is empty in every row is dropped. A ``Table N``
line just above a table is its caption and stays with it.
A picture inside a table stays its own image, and the table keeps its text.
A table that contains another table is kept as one picture of that region.
A drawing such as a flowchart, where three or more drawn boxes holding
text are joined by lines or arrows, is kept as one picture of that region
too, and its words stay in the picture. A letter printed several times
over itself to look bold is read once. A line or table repeated in the
margin of at least a third of the pages is left out, and a page number in
that line may change from page to page. A short line repeated at the top or bottom of
most pages is left out too, as is a contents line of dot leaders ending in
a page number. Bullet lines become one list, nested when a bullet is set in
from the current one. A bullet glyph or a paragraph number set apart from
its text, as in a hanging indent or a margin, is joined to that text. A
page number in the margin is left out. A paragraph cut off at the foot of
a page continues on the next page when it ends mid-sentence and the next
page starts in lowercase, and a list cut off the same way continues as one
list. A heading is a line
larger than the body, a bold line that is also larger, an outline entry, or
a numbered section title. A numbered line such as ``1. Mounting Position``
is a title only when it is set in bold; a plain one is a list item. A
paragraph number from the margin never makes a plain line a title, and
neither does a line of author names under a paper's title. Wrapped
lines of one title are joined. The largest heading size is level 1, and a
bold numbered title at body size sits under every sized heading, with
``1-1.`` one level under ``1.``.
"""

import math
import re
from collections import Counter
from io import BytesIO
from statistics import median
from typing import NamedTuple

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException

from ragbytes.extract.render import (
    normalize_inline,
    render_complex,
    render_image,
    render_paragraph,
    render_table,
)
from pdfminer.layout import LTChar, LTContainer, LTImage
from pdfminer.pdfdocument import PDFNoOutlines
from pdfminer.pdfparser import PDFSyntaxError
from pdfminer.psexceptions import PSEOF

from ragbytes.extract.pdf_clipping import Clipped, clipped_chars, open_document
from ragbytes.extract.pdf_drawings import find_drawings
from ragbytes.extract.sections import (
    TABLE_LABEL,
    HeadingState,
    add_section,
    assign_indexes,
    looks_like_heading,
)
from ragbytes.schemas import Section

_PAGE_NUMBER = re.compile(
    r"^(?:(?:page\s+)?\d{1,4}(?:\s+of\s+\d{1,4})?|of\s+\d{1,4})$", re.IGNORECASE
)
_BULLET = re.compile(r"^(?:[•●▪◦‣・*]|\-)\s+(\S.*)$")
_NUMBERED = re.compile(r"^(\d{1,3}(?:-\d{1,3})*[.)])\s+(\S.*)$")
_NUMBERED_TITLE = re.compile(r"^(\d{1,3}(?:-\d{1,3})*)[.)]\s+\S")
_MULTINUM = re.compile(r"^(\d+(?:\.\d+)+)\.?\s+\S")
_CHAPTER = re.compile(r"^(?:chapter|part|appendix)\b", re.IGNORECASE)
_SECTION_NUMBER = re.compile(r"^\d{1,3}(?:\.\d{1,3})*\.?\s+\S")
_TITLE_SCALE = 1.25
_BOLD_TITLE_WORDS = 10
_MIN_TITLE_LETTERS = 4
_SMALL_WORDS = frozenset({"a", "an", "and", "as", "at", "for", "in", "of", "on", "or", "the", "to", "vs"})
_SECTION_WORD = re.compile(r"^section\b", re.IGNORECASE)
_FIGURE = re.compile(r"^(?:figure|fig\.?)\s+\d+\b", re.IGNORECASE)
_BOLD_FONT = re.compile(r"bold|black|heavy|semibold|demi|medi|cmbx", re.IGNORECASE)
_TOC_LINE = re.compile(r"(?:\.\s?){4,}\s*\d{1,4}$")
_SIDE_LABEL = re.compile(
    r"^(?:\d{1,3}(?:\.\d{1,3})+\.?|\d{1,3}[.)]|\(\d{1,3}\)|[A-Za-z][.)]|\([A-Za-z]\))$"
)
_MARKER_GLYPHS = frozenset("•●▪◦‣・*–-§■□○◆◇►▶➢➤✓✔")
_LETTER_BULLETS = frozenset("oO")
_SENTENCE_END = (".", "!", "?", ":", ";", '"', "”", "’", ")", "]")
_CAPTION_LIMIT = 160
_MIN_IMAGE = 24
_MIN_GUTTER = 12
_MAX_WORD_GAP = _MIN_GUTTER - 1
_MAX_LABEL_GAP = 60.0
_CHROME_PREFIX = 40
_CHROME_SHARE = 0.3
_OVERPRINT_SLACK = 1.0
_CHROME_SIZE_SLACK = 2.0
_LIST_INDENT = 8
_MIN_OVERLAP = 24
_MIN_SIDE = 2
_MIN_SIDE_CHARS = 40
_MIN_LINE_WIDTH = 40
_EDGE_SLACK = 1.5
_EDGE_MARGIN = 6.0
_EDGE_SUPPORT = 3
_WORD_GAP_RATIO = 0.15
_TIGHT_JOIN = 0.08
_FIGURE_CAPTION_LIMIT = 600
_BACKDROP_WORDS = 8
_BACKDROP_WIDTH = 0.75
_BACKDROP_TEXT = 30
_SCANNED_COVER = 0.5
_UNIT_GAP_LINES = 3.0
_GUTTER_CROSSINGS = 20
_MIN_UNIT_GAP = 30.0
_NAME_WORD = re.compile(
    r"^(?:[A-Z][\w'’.-]*|and|bin|da|de|del|della|den|der|di|du|la|le|van|von|[*†‡∗\d,]+)$"
)
_EMAIL_DOMAIN = re.compile(r"@\s?[\w-]+(?:\.[\w-]+)+")
_BYLINE_STOP = re.compile(r"\b(?:contact|email|e-mail|support|about|enquiries|questions|help)\b", re.IGNORECASE)
_BYLINE_LOOKAHEAD = 5
_BASELINE_SLIP = 0.35
_CLOSING_MARKS = frozenset(",.;:!?%)]}”’")
_OPENING_MARKS = frozenset("([{“‘")


class _Block(NamedTuple):
    top: float
    bottom: float
    x0: float
    x1: float
    kind: str
    payload: object


class _Figure(NamedTuple):
    """A picture on the page: cropped PNG bytes, and the words of a flowchart drawn there."""

    media: bytes | None
    text: str = ""


def extract_pdf(data: bytes) -> list[Section]:
    """Convert a PDF into heading-labeled sections.

    Each embedded image is cropped from its page and stored as PNG bytes.
    """
    try:
        return _extract_pdf(data)
    except PdfminerException as exc:
        raise ValueError("Could not read the PDF.") from exc


def _extract_pdf(data: bytes) -> list[Section]:
    pages: list[tuple[int, float, tuple]] = []
    outlines: dict[str, int] = {}
    document = open_document(data)
    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            outlines = _outline_levels(pdf)
            for page_number, page in enumerate(pdf.pages, start=1):
                clipped = clipped_chars(document, page_number - 1)
                page = _without_overprint(page)
                pages.append((page_number, float(page.height), _capture_page(page, clipped)))
    finally:
        if document is not None:
            document.close()

    body_size = _body_size(pages)
    chrome = _margin_chrome(pages)
    repeats = _running_titles(pages)
    candidates = _heading_candidates(pages, body_size, chrome, repeats, outlines)
    outlines = _outlines_under_cover(candidates, body_size, outlines)
    scale = _heading_scale(candidates, body_size)
    state = HeadingState()
    sections: list[Section] = []
    for page_number, height, (words, tables, images) in pages:
        visible = _without_chrome_tables(tables, height, chrome)
        page_sections = _page_blocks(
            words,
            visible,
            images,
            body_size,
            state,
            page_number,
            height,
            chrome,
            scale,
            outlines,
            repeats,
        )
        _join_across_pages(sections, page_sections)
        sections.extend(page_sections)
    return assign_indexes(sections)


def _join_across_pages(previous: list[Section], following: list[Section]) -> None:
    """Rejoin a paragraph, a list, or a list's lead-in that a page break cut apart.

    The last section before the break and the first after it must sit under
    the same headings on consecutive pages. A paragraph continues when it
    ends mid-sentence and the next page goes on in lowercase or after a comma.
    A lead-in ending with a colon joins the list after it, and a list split by
    the break becomes one list.
    """
    if not previous or not following:
        return
    last = previous[-1]
    first = following[0]
    if last.page is None or first.page != last.page + 1 or last.headings != first.headings:
        return
    if last.kind == "text" and first.kind == "text":
        if _continues_sentence(last.data, first.data):
            last.data = _join_wrapped([last.data, first.data])
            following.pop(0)
        return
    if last.kind == "text" and first.kind == "list":
        if last.data.endswith(":"):
            first.data = f"{last.data}\n{first.data}"
        elif _continues_sentence(last.data, first.data) and not first.data.startswith("- "):
            first.data = _join_wrapped([last.data, first.data])
        else:
            return
        first.page = last.page
        previous.pop()
        return
    if last.kind == "list" and first.kind == "list":
        last.data = f"{last.data}\n{first.data}"
        following.pop(0)
        return
    if last.kind == "list" and first.kind == "text":
        item = last.data.rsplit("\n", 1)[-1]
        if _continues_sentence(item, first.data):
            last.data = _join_wrapped([last.data, first.data])
            following.pop(0)


def _continues_sentence(before: str, after: str) -> bool:
    before = before.rstrip()
    if not before or not after or before.endswith(_SENTENCE_END):
        return False
    return after[:1].islower() or before.endswith((",", "-")) or after[:1] == "("


def _without_overprint(page):
    """Drop a letter printed again on top of itself, as a fake bold does."""
    placed: dict[tuple, list[tuple[float, float]]] = {}
    repeats: set[int] = set()
    for char in page.chars:
        x, y = float(char["x0"]), float(char["top"])
        key = (char.get("text"), char.get("fontname"), round(float(char.get("size") or 0), 1))
        cell = (int(x // _OVERPRINT_SLACK), int(y // _OVERPRINT_SLACK))
        if any(
            abs(x - px) <= _OVERPRINT_SLACK and abs(y - py) <= _OVERPRINT_SLACK
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for px, py in placed.get((*key, cell[0] + dx, cell[1] + dy), ())
        ):
            repeats.add(id(char))
            continue
        placed.setdefault((*key, *cell), []).append((x, y))
    if not repeats:
        return page
    return page.filter(lambda obj: id(obj) not in repeats)


def _capture_page(
    page, clipped: Clipped | None = None
) -> tuple[list[dict], list[tuple], list[tuple[tuple, _Figure]]]:
    words = _page_words(page, return_chars=True, clipped=clipped)
    raw_images = []
    for image in page.images or []:
        if (image.get("width") or 0) < _MIN_IMAGE or (image.get("height") or 0) < _MIN_IMAGE:
            continue
        box = _image_box(image)
        if box is None:
            continue
        raw_images.append((box, image))
    if not words and _is_scanned(page, raw_images):
        return [], [(_page_box(page), "complex", _safe_crop(page, _page_box(page)))], []
    words = _without_hidden_words(page, words, raw_images)
    raw_images = [
        (box, image) for box, image in raw_images if not _is_backdrop(box, words, float(page.width))
    ]
    raw_tables = _find_tables(page, words)
    tables, kept_images, covered_boxes = _package_tables(page, raw_tables, raw_images)
    images: list[tuple[tuple[float, float, float, float], _Figure]] = []
    for box, _image in kept_images:
        images.append((box, _Figure(_safe_crop(page, box))))
    excluded = [bbox for bbox, _kind, _payload in tables] + [box for box, _ in images]
    for drawing in find_drawings(page, words, excluded):
        images.append((drawing.box, _Figure(_safe_crop(page, drawing.box), drawing.text)))
    for word in words:
        word.pop("chars", None)
    return _outside_tables(words, covered_boxes), tables, images


def _page_words(page, *, return_chars: bool = False, clipped: Clipped | None = None) -> list[dict]:
    """Words set upright on the page.

    The gap that separates two words scales with the font size, so tightly
    set text without space characters still splits into words. Text turned
    on its side, such as an arXiv stamp in the margin, is left out, and so
    is text its clipping path hides.
    """
    source = page
    if clipped:
        source = page.filter(lambda item: item.get("object_type") != "char" or not clipped.hides(item))
    words = (
        source.extract_words(
            extra_attrs=["fontname", "size"],
            x_tolerance_ratio=_WORD_GAP_RATIO,
            return_chars=True,
        )
        or []
    )
    words = [word for word in words if word.get("upright", True)]
    _align_to_baselines(page, words)
    if not return_chars:
        for word in words:
            word.pop("chars", None)
    return words


def _align_to_baselines(page, words: list[dict]) -> None:
    """Move a word whose box disagrees with its baseline back onto its line.

    Some maths fonts report a glyph box far above or below where the glyph
    is set, which would put a symbol such as a calligraphic H on the next
    line. The baseline the text is set on is reliable, so a word whose top
    sits much further from its baseline than is usual on the page moves to
    where its baseline puts it.
    """
    height = float(page.height)
    offsets: list[float | None] = []
    for word in words:
        baselines = [
            height - float(char["matrix"][5])
            for char in word.get("chars") or []
            if char.get("matrix")
        ]
        size = float(word.get("size") or 0)
        if not baselines or size <= 0:
            offsets.append(None)
            continue
        offsets.append((median(baselines) - float(word["top"])) / size)
    usual = [offset for offset in offsets if offset is not None]
    if not usual:
        return
    expected = median(usual)
    for word, offset in zip(words, offsets):
        if offset is None or abs(offset - expected) <= _BASELINE_SLIP:
            continue
        shift = (offset - expected) * float(word.get("size") or 0)
        for key in ("top", "bottom", "doctop"):
            if key in word:
                word[key] = float(word[key]) + shift


def _is_scanned(page, raw_images) -> bool:
    """A page with no text and a picture over most of it is a scan."""
    area = float(page.width) * float(page.height)
    return area > 0 and any(_box_area(box) >= area * _SCANNED_COVER for box, _image in raw_images)


def _without_hidden_words(page, words: list[dict], raw_images) -> list[dict]:
    """Drop words that something painted later covers, since a reader never sees them.

    A picture can cover text drawn before it, and where two words sit on the
    same spot only the one painted last shows. A word set twice in the same
    font and size, slightly apart, is a faked bold or a shadow, and only the
    copy painted last is kept.
    """
    covered = [
        (box, image)
        for box, image in raw_images
        if any(_center_inside(_word_box(word), box) for word in words)
    ]
    clashes = _overlapping_words(words) + _offset_copies(words)
    if not covered and not clashes:
        return words
    char_order, image_order = _draw_order(page)

    def painted_at(word: dict) -> int | None:
        drawn = [char_order.get(id(char)) for char in word.get("chars") or []]
        if not drawn or any(order is None for order in drawn):
            return None
        return max(drawn)

    hidden: set[int] = set()
    for first, second in clashes:
        if first in hidden or second in hidden:
            continue
        first_at, second_at = painted_at(words[first]), painted_at(words[second])
        if first_at is not None and second_at is not None:
            hidden.add(first if first_at < second_at else second)
    for box, image in covered:
        painted = image_order.get(id(image))
        if painted is None:
            continue
        for index, word in enumerate(words):
            if not _center_inside(_word_box(word), box):
                continue
            word_at = painted_at(word)
            if word_at is not None and word_at < painted:
                hidden.add(index)
    return [word for index, word in enumerate(words) if index not in hidden]


def _overlapping_words(words: list[dict]) -> list[tuple[int, int]]:
    """Pairs of words that share most of the smaller word's area."""
    order = sorted(range(len(words)), key=lambda index: float(words[index]["x0"]))
    pairs: list[tuple[int, int]] = []
    for position, first in enumerate(order):
        box = _word_box(words[first])
        for second in order[position + 1 :]:
            other = _word_box(words[second])
            if other[0] >= box[2]:
                break
            shared = _box_area(
                (max(box[0], other[0]), max(box[1], other[1]), min(box[2], other[2]), min(box[3], other[3]))
            )
            smaller = min(_box_area(box), _box_area(other))
            if smaller > 0 and shared >= smaller * 0.5:
                pairs.append((first, second))
    return pairs


def _offset_copies(words: list[dict]) -> list[tuple[int, int]]:
    """Pairs of words with the same text, font and size whose boxes touch but share less than half."""
    order = sorted(range(len(words)), key=lambda index: float(words[index]["x0"]))
    pairs: list[tuple[int, int]] = []
    for position, first in enumerate(order):
        word = words[first]
        box = _word_box(word)
        for second in order[position + 1 :]:
            other_word = words[second]
            other = _word_box(other_word)
            if other[0] >= box[2]:
                break
            if (
                other_word["text"] != word["text"]
                or other_word.get("fontname") != word.get("fontname")
                or abs(float(other_word.get("size") or 0) - float(word.get("size") or 0)) > 0.1
            ):
                continue
            shared = _box_area(
                (max(box[0], other[0]), max(box[1], other[1]), min(box[2], other[2]), min(box[3], other[3]))
            )
            if 0 < shared < min(_box_area(box), _box_area(other)) * 0.5:
                pairs.append((first, second))
    return pairs


def _draw_order(page) -> tuple[dict[int, int], dict[int, int]]:
    """Number each character and picture in the order the page paints them."""
    chars = iter(page.chars)
    images = iter(page.images)
    char_order: dict[int, int] = {}
    image_order: dict[int, int] = {}
    counter = 0

    def walk(objects) -> None:
        nonlocal counter
        for item in objects:
            if isinstance(item, LTContainer):
                walk(item)
                continue
            counter += 1
            if isinstance(item, LTChar):
                char = next(chars, None)
                if char is not None:
                    char_order[id(char)] = counter
            elif isinstance(item, LTImage):
                image = next(images, None)
                if image is not None:
                    image_order[id(image)] = counter

    walk(page.layout)
    return char_order, image_order


def _is_backdrop(box, words: list[dict], page_width: float) -> bool:
    """A picture set behind running text, such as a banner, is decoration and its words are text."""
    on_top = [word for word in words if _center_inside(_word_box(word), box)]
    if len(on_top) < _BACKDROP_WORDS:
        return False
    return box[2] - box[0] >= page_width * _BACKDROP_WIDTH or len(on_top) >= _BACKDROP_TEXT


def _page_box(page) -> tuple[float, float, float, float]:
    x0, top, x1, bottom = page.bbox
    return float(x0), float(top), float(x1), float(bottom)


def _safe_crop(page, box) -> bytes | None:
    try:
        return _crop_box(page, box)
    except (TypeError, ValueError, OSError):
        return None


def _find_tables(page, words: list[dict]) -> list[tuple[tuple, str | None]]:
    """Return the tabular regions on this page, each with its rendered rows.

    A ruled page is not a table. A frame around the page, a rule under a
    title, or a box beside a paragraph all draw edges, and the default finder
    joins them into one grid that swallows the page. Here an edge that slices
    through more words than it separates is dropped first, then each grid is
    read row by row. A row whose text sits in two or more columns is tabular.
    A row with one wide cell is prose and its words stay in the text flow.
    Consecutive tabular rows form one table.
    """
    edges = _table_edges(page, words)
    vertical = [edge for edge in edges if edge["orientation"] == "v"]
    horizontal = [edge for edge in edges if edge["orientation"] == "h"]
    if len(vertical) < 2 or len(horizontal) < 2:
        return []
    settings = {
        "vertical_strategy": "explicit",
        "horizontal_strategy": "explicit",
        "explicit_vertical_lines": vertical,
        "explicit_horizontal_lines": horizontal,
    }
    try:
        grids = page.find_tables(settings) or []
    except (TypeError, ValueError):
        return []
    found: list[tuple[tuple, str | None]] = []
    for grid in grids:
        for rows in _tabular_runs(grid, words):
            box = _rows_box(rows)
            cells = _trim_columns([_row_cells(row, words) for row in rows])
            cells = _merge_continued_rows(_merge_spill_columns(cells))
            rendered = render_table(cells)
            if rendered:
                found.append((box, rendered))
    return found


def _table_edges(page, words: list[dict]) -> list[dict]:
    """Return the page's edges, without the ones that slice through text.

    A real column rule has many words ending just before it or starting just
    after it, and slices through a word only when two cell values are set
    with no space between them. An edge that slices through words and has
    few words beside it is a box or a rule, not a column.
    """
    kept: list[dict] = []
    for edge in page.edges or []:
        cut = 0
        supported = 0
        for word in words:
            relation = _edge_relation(edge, word)
            if relation == "cut":
                cut += 1
            elif relation == "beside":
                supported += 1
        if cut and supported < cut * _EDGE_SUPPORT:
            continue
        kept.append(edge)
    return kept


def _edge_relation(edge: dict, word: dict) -> str | None:
    """Return ``cut`` when the edge passes through the word, ``beside`` when it borders it."""
    if edge["orientation"] == "v":
        if not (float(word["top"]) < float(edge["bottom"]) and float(word["bottom"]) > float(edge["top"])):
            return None
        x = float(edge["x0"])
        x0, x1 = float(word["x0"]), float(word["x1"])
        if x0 + _EDGE_SLACK < x < x1 - _EDGE_SLACK:
            return "cut"
        if abs(x - x0) <= _EDGE_MARGIN or abs(x - x1) <= _EDGE_MARGIN:
            return "beside"
        return None
    if not (float(word["x0"]) < float(edge["x1"]) and float(word["x1"]) > float(edge["x0"])):
        return None
    y = float(edge["top"])
    top, bottom = float(word["top"]), float(word["bottom"])
    if top + _EDGE_SLACK < y < bottom - _EDGE_SLACK:
        return "cut"
    if abs(y - top) <= _EDGE_MARGIN or abs(y - bottom) <= _EDGE_MARGIN:
        return "beside"
    return None


def _tabular_runs(grid, words: list[dict]) -> list[list]:
    """Split one detected grid into runs of rows that read as a table."""
    rows = list(grid.rows)
    filled = [_filled_cells(row, words) for row in rows]
    kinds: list[str] = []
    for row, cells in zip(rows, filled, strict=True):
        geometry = sum(1 for cell in row.cells if cell is not None)
        if geometry < 2:
            kinds.append("prose")
        elif len(cells) >= 2:
            kinds.append("table")
        elif len(cells) == 1:
            kinds.append("sparse")
        else:
            kinds.append("empty")
    _absorb_sparse_rows(rows, filled, kinds)
    runs: list[list] = []
    current: list[tuple] = []
    for row, kind in zip(rows, kinds, strict=True):
        if kind == "table" or (kind == "empty" and current):
            current.append((row, kind))
            continue
        if current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    kept: list[list] = []
    for run in runs:
        while run and run[-1][1] == "empty":
            run.pop()
        rows_only = [row for row, _kind in run]
        if _is_table_run(rows_only, words):
            kept.append(rows_only)
    return kept


def _absorb_sparse_rows(rows: list, filled: list[list], kinds: list[str]) -> None:
    """A row with one filled cell joins the table beside it when that cell is one column wide."""
    changed = True
    while changed:
        changed = False
        for index, kind in enumerate(kinds):
            if kind != "sparse":
                continue
            neighbors = [
                rows[other]
                for other in (index - 1, index + 1)
                if 0 <= other < len(rows) and kinds[other] == "table"
            ]
            if not neighbors:
                continue
            cell = filled[index][0]
            if any(_spans_one_column(cell, neighbor) for neighbor in neighbors):
                kinds[index] = "table"
                changed = True


def _spans_one_column(cell, neighbor) -> bool:
    x0, _top, x1, _bottom = cell
    boundaries = set()
    for other in neighbor.cells:
        if other is None:
            continue
        boundaries.add(round(float(other[0]), 1))
        boundaries.add(round(float(other[2]), 1))
    return not any(x0 + _EDGE_SLACK < boundary < x1 - _EDGE_SLACK for boundary in boundaries)


def _is_table_run(rows: list, words: list[dict]) -> bool:
    if len(rows) < 2:
        return False
    columns: set[float] = set()
    for row in rows:
        for cell in _filled_cells(row, words):
            columns.add(round(float(cell[0]), 1))
    return len(columns) >= 2


def _filled_cells(row, words: list[dict]) -> list:
    return [
        cell
        for cell in row.cells
        if cell is not None and any(_center_inside(_word_box(word), cell) for word in words)
    ]


def _rows_box(rows: list) -> tuple[float, float, float, float]:
    boxes = [_as_box(cell) for row in rows for cell in row.cells if cell is not None]
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _row_cells(row, words: list[dict]) -> list[str]:
    """Read each cell from the words whose center sits inside it.

    A word that straddles a kept column edge is split at that edge, so two
    cell values set without a space between them still land in their cells.
    """
    cells = [cell for cell in row.cells if cell is not None]
    boundaries = sorted({round(float(x), 1) for cell in cells for x in (cell[0], cell[2])})
    band = _rows_box([row])
    pieces: list[dict] = []
    for word in words:
        box = _word_box(word)
        if not _center_inside(box, band):
            continue
        pieces.extend(_split_word(word, boundaries))
    texts: list[str] = []
    for cell in row.cells:
        if cell is None:
            texts.append("")
            continue
        inside = [piece for piece in pieces if _center_inside(_word_box(piece), cell)]
        texts.append(" ".join(line["text"] for line in _lines(inside)))
    return texts


def _split_word(word: dict, boundaries: list[float]) -> list[dict]:
    x0, x1 = float(word["x0"]), float(word["x1"])
    cuts = [x for x in boundaries if x0 + _EDGE_SLACK < x < x1 - _EDGE_SLACK]
    chars = word.get("chars")
    if not cuts or not chars:
        return [word]
    groups: list[list[dict]] = [[] for _ in range(len(cuts) + 1)]
    for char in chars:
        center = (float(char["x0"]) + float(char["x1"])) / 2
        slot = sum(1 for x in cuts if center >= x)
        groups[slot].append(char)
    pieces: list[dict] = []
    for group in groups:
        text = "".join(char.get("text") or "" for char in group).strip()
        if not text:
            continue
        pieces.append(
            {
                **{key: value for key, value in word.items() if key != "chars"},
                "text": text,
                "x0": min(float(char["x0"]) for char in group),
                "x1": max(float(char["x1"]) for char in group),
            }
        )
    return pieces or [word]


def _word_box(word: dict) -> tuple[float, float, float, float]:
    return float(word["x0"]), float(word["top"]), float(word["x1"]), float(word["bottom"])


def _trim_columns(rows: list[list[str]]) -> list[list[str]]:
    """Drop columns that are empty in every row."""
    if not rows:
        return rows
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    kept = [index for index in range(width) if any(row[index].strip() for row in padded)]
    return [[row[index] for index in kept] for row in padded]


def _merge_spill_columns(rows: list[list[str]]) -> list[list[str]]:
    """Fold a headless column into the column on its left when no row fills both.

    A stray ruling edge can cut a sliver column off the side of a wide cell,
    so a wrapped line of that cell lands in a column of its own.
    """
    if len(rows) < 2:
        return rows
    rows = [list(row) for row in rows]
    column = 1
    while rows and column < len(rows[0]):
        clash = any(row[column].strip() and row[column - 1].strip() for row in rows)
        if rows[0][column].strip() or clash:
            column += 1
            continue
        for row in rows:
            row[column - 1] = row[column - 1] or row[column]
            del row[column]
    return rows


def _merge_continued_rows(rows: list[list[str]]) -> list[list[str]]:
    """A row holding one lowercase fragment under a filled cell continues that cell."""
    merged: list[list[str]] = []
    for row in rows:
        filled = [index for index, cell in enumerate(row) if cell.strip()]
        if merged and len(filled) == 1:
            index = filled[0]
            above = merged[-1][index] if index < len(merged[-1]) else ""
            text = row[index].strip()
            if above.strip() and text[:1].islower() and not above.rstrip().endswith(_SENTENCE_END[:3]):
                merged[-1][index] = f"{above.rstrip()} {text}"
                continue
        merged.append(list(row))
    return merged


def _package_tables(page, raw_tables, raw_images):
    """Keep a nested layout as one picture. A picture in a flat table stays separate.

    Words drawn on that picture are removed from the table text. A smaller
    table inside a larger one, and the pictures inside that layout, stay in
    the one picture of the outer table.
    """
    image_boxes = [box for box, _image in raw_images]
    nested = {
        index
        for index, (box, _rendered) in enumerate(raw_tables)
        if any(
            _is_nested_box(box, other)
            for other_index, (other, _other) in enumerate(raw_tables)
            if other_index != index
        )
    }
    tables = []
    complex_boxes = []
    for index, (box, rendered) in enumerate(raw_tables):
        if index in nested:
            continue
        inside = [image_box for image_box in image_boxes if _center_inside(image_box, box)]
        if _contains_nested_table(box, raw_tables, index):
            try:
                media = _crop_box(page, box)
            except (TypeError, ValueError, OSError):
                media = None
            tables.append((box, "complex", media))
            complex_boxes.append(box)
            continue
        if inside and rendered:
            rendered = _without_picture_text(page, box, inside, rendered)
        if rendered and rendered.strip():
            tables.append((box, "table", rendered))
    kept = []
    covered = []
    for box, image in raw_images:
        if any(_center_inside(box, region) for region in complex_boxes):
            covered.append(box)
            continue
        kept.append((box, image))
    return tables, kept, covered


def _contains_nested_table(box, raw_tables, index: int) -> bool:
    return any(
        _is_nested_box(other, box)
        for other_index, (other, _rendered) in enumerate(raw_tables)
        if other_index != index
    )


def _without_picture_text(page, table_box, image_boxes, rendered: str) -> str:
    """Remove words that sit on a picture from the table's text."""
    hidden: list[str] = []
    for word in _page_words(page):
        text = normalize_inline(word.get("text") or "")
        if not text:
            continue
        box = (
            float(word["x0"]),
            float(word["top"]),
            float(word["x1"]),
            float(word["bottom"]),
        )
        if _center_inside(box, table_box) and any(_center_inside(box, image) for image in image_boxes):
            hidden.append(text)
    if not hidden:
        return rendered
    phrase = normalize_inline(" ".join(hidden))
    lines: list[str] = []
    for line in rendered.split("\n"):
        if not line.startswith("|"):
            lines.append(line)
            continue
        cells = []
        for cell in line.split("|"):
            cleaned = cell.replace(phrase, "") if phrase else cell
            for text in hidden:
                cleaned = cleaned.replace(text, "")
            cells.append(re.sub(r" {2,}", " ", cleaned))
        lines.append("|".join(cells))
    return "\n".join(lines)


def _is_nested_box(inner, outer) -> bool:
    inner_area = _box_area(inner)
    outer_area = _box_area(outer)
    if inner_area <= 0 or inner_area >= outer_area * 0.98:
        return False
    return _center_inside(inner, outer)


def _center_inside(inner, outer) -> bool:
    x0, top, x1, bottom = inner
    center_x = (x0 + x1) / 2
    center_y = (top + bottom) / 2
    ox0, otop, ox1, obottom = outer
    return ox0 <= center_x <= ox1 and otop <= center_y <= obottom


def _box_area(box) -> float:
    x0, top, x1, bottom = box
    return max(x1 - x0, 0.0) * max(bottom - top, 0.0)


def _as_box(box) -> tuple[float, float, float, float]:
    x0, top, x1, bottom = (float(value) for value in box)
    if x1 < x0:
        x0, x1 = x1, x0
    if bottom < top:
        top, bottom = bottom, top
    return x0, top, x1, bottom


def _crop_box(page, box) -> bytes | None:
    x0, top, x1, bottom = _as_box(box)
    px0, ptop, px1, pbottom = page.bbox
    x0 = max(x0, float(px0))
    top = max(top, float(ptop))
    x1 = min(x1, float(px1))
    bottom = min(bottom, float(pbottom))
    if x1 - x0 < 1 or bottom - top < 1:
        return None
    rendered = page.crop((x0, top, x1, bottom)).to_image(resolution=144)
    buffer = BytesIO()
    rendered.original.save(buffer, format="PNG")
    payload = buffer.getvalue()
    if not payload:
        return None
    return payload


def _page_blocks(
    words,
    tables,
    images,
    body_size: float,
    state: HeadingState,
    page_number: int,
    height: float,
    chrome: dict[str, float],
    scale: dict[float, int],
    outlines: dict[str, int],
    repeats: set[str],
) -> list[Section]:
    sections: list[Section] = []
    items = _ordered_blocks(words, tables, images)
    paragraph: list[str] = []
    paragraph_bottom: float | None = None
    line_gap: float | None = None
    list_items: list[str] = []
    bullet_levels: list[float] = []
    bullet_x: float | None = None
    bullet_bottom: float | None = None
    bullet_gap: float | None = None
    last_top: float | None = None
    previous_bottom: float | None = None

    def flush() -> None:
        nonlocal paragraph_bottom, line_gap
        if not paragraph:
            return
        rendered = render_paragraph(_join_wrapped(paragraph))
        paragraph.clear()
        paragraph_bottom = None
        line_gap = None
        if rendered:
            add_section(sections, "text", rendered, state, page=page_number)

    def flush_list() -> None:
        nonlocal bullet_x, bullet_bottom, bullet_gap
        if list_items:
            add_section(sections, "list", "\n".join(list_items), state, page=page_number)
            list_items.clear()
        bullet_levels.clear()
        bullet_x = None
        bullet_bottom = None
        bullet_gap = None

    def add_item(body: str, origin: float, bottom: float) -> None:
        nonlocal bullet_x, bullet_bottom, bullet_gap
        rendered = render_paragraph(body)
        if not rendered:
            return
        flush()
        while bullet_levels and origin < bullet_levels[-1] - _LIST_INDENT:
            bullet_levels.pop()
        if not bullet_levels or origin > bullet_levels[-1] + _LIST_INDENT:
            bullet_levels.append(origin)
        depth = min(len(bullet_levels) - 1, 8)
        list_items.append(f"{'  ' * depth}- {rendered}")
        bullet_x = origin
        bullet_bottom = bottom
        bullet_gap = None

    index = 0
    while index < len(items):
        block = items[index]
        kind = block.kind
        payload = block.payload
        if kind in {"table", "complex"}:
            flush()
            flush_list()
            previous_bottom = float(block.bottom)
            if kind == "complex":
                media = payload if isinstance(payload, bytes) else None
                add_section(
                    sections,
                    "complex",
                    render_complex(),
                    state,
                    page=page_number,
                    media=media,
                    media_type="image/png" if media else None,
                )
            else:
                add_section(sections, "table", str(payload), state, page=page_number)
            index += 1
            continue
        if kind == "image":
            flush()
            flush_list()
            lead = _take_figure_lead(sections, state, page_number)
            follow, skip = _following_caption(
                items, index, body_size, height, chrome, outlines, repeats
            )
            caption = _join_wrapped([part for part in (lead, follow) if part])
            figure = payload if isinstance(payload, _Figure) else _Figure(None)
            media = figure.media
            description = " ".join(part for part in (caption, figure.text) if part)
            add_section(
                sections,
                "image",
                render_image(description or None),
                state,
                page=page_number,
                media=media,
                media_type="image/png" if media else None,
            )
            if skip:
                skipped = items[index + skip]
                if skipped.kind == "text" and isinstance(skipped.payload, dict):
                    last_top = skipped.payload["top"]
                    previous_bottom = float(skipped.payload["bottom"])
            else:
                previous_bottom = None
            index += 1 + skip
            continue
        line = payload
        text = line["text"]
        if not text:
            index += 1
            continue
        if _is_margin_chrome(line, height, chrome):
            index += 1
            continue
        if _is_page_number(line, body_size) and _in_margin(line["top"], line["bottom"], height):
            index += 1
            continue
        if _is_running_title(line, height, repeats):
            index += 1
            continue
        if _TOC_LINE.search(text):
            index += 1
            continue
        if last_top is not None and line["top"] + 2 < last_top:
            flush()
            flush_list()
            previous_bottom = None
        last_top = line["top"]
        bullet = _BULLET.match(text)
        if bullet is not None:
            add_item(bullet.group(1), line["x0"], line["bottom"])
            previous_bottom = float(line["bottom"])
            index += 1
            continue
        matched = _candidate_heading(
            items, index, previous_bottom, body_size, height, chrome, repeats, outlines
        )
        if matched is not None:
            merged, count = matched
            flush()
            flush_list()
            level = _assigned_level(merged, body_size, scale, outlines)
            state.apply(_consistent_level(state, merged["text"], level), merged["text"])
            last_top = merged["last_top"]
            previous_bottom = merged["bottom"]
            index += count
            continue
        numbered = _NUMBERED.match(text)
        if numbered is not None:
            add_item(numbered.group(2), line["x0"], line["bottom"])
            previous_bottom = float(line["bottom"])
            index += 1
            continue
        if list_items and bullet_bottom is not None:
            gap = line["top"] - bullet_bottom
            indented = line["x0"] > (bullet_x or 0) + _LIST_INDENT
            hanging = (
                line["x0"] >= (bullet_x or 0) - 1
                and gap <= line["size"] * 0.5
                and _continues_sentence(list_items[-1], text)
            )
            if (indented or hanging) and not _starts_paragraph(gap, line["size"], bullet_gap):
                extra = render_paragraph(text)
                if extra:
                    list_items[-1] = _join_wrapped([list_items[-1], extra])
                if bullet_gap is None and gap > 0:
                    bullet_gap = gap
                bullet_bottom = line["bottom"]
                previous_bottom = float(line["bottom"])
                index += 1
                continue
            flush_list()
        if paragraph and paragraph_bottom is not None:
            gap = line["top"] - paragraph_bottom
            if _starts_paragraph(gap, line["size"], line_gap):
                flush()
            elif line_gap is None and gap > 0:
                line_gap = gap
        paragraph.append(text)
        paragraph_bottom = line["bottom"]
        previous_bottom = float(line["bottom"])
        index += 1

    flush()
    flush_list()
    return sections


def _ordered_blocks(words, tables, images) -> list[_Block]:
    """Return this page's blocks in reading order.

    One cluster of text stays top to bottom. A clear vertical gap splits the
    page into columns, and each column is read from top to bottom before the
    next column starts. A block that crosses the gap, such as a title or a
    full-width table, stays between the column bands it divides. Words whose
    center sits on an embedded image are left out.
    """
    figure_boxes = [box for box, _ in images]
    body = _outside_tables(words, [bbox for bbox, _kind, _payload in tables])
    body = _outside_tables(body, figure_boxes)
    blocks = [_text_block(line) for line in _lines(body)]
    for bbox, kind, payload in tables:
        blocks.append(_box_block(bbox, kind, payload))
    for box, figure in images:
        blocks.append(_box_block(box, "image", figure))
    return _order_region(blocks)


def _text_block(line: dict) -> _Block:
    return _Block(line["top"], line["bottom"], line["x0"], line["x1"], "text", line)


def _box_block(box, kind: str, payload) -> _Block:
    x0, top, x1, bottom = box
    return _Block(float(top), float(bottom), float(x0), float(x1), kind, payload)


def _order_region(blocks: list[_Block]) -> list[_Block]:
    units = _stacked_units(blocks)
    if len(units) > 1:
        return [block for unit in units for block in _order_region(unit)]
    gutter = _find_gutter(blocks)
    if gutter is None:
        return sorted(blocks, key=lambda block: (block.top, block.kind != "text", block.x0))
    left, right, spans = _partition(blocks, gutter)
    if not left or not right or max(len(left), len(right)) >= len(blocks):
        return sorted(blocks, key=lambda block: (block.top, block.kind != "text", block.x0))
    return _read_columns(left, right, spans)


def _stacked_units(blocks: list[_Block]) -> list[list[_Block]]:
    """Split the page where an empty band runs across its full width.

    Handouts print several slides on one page, each with its own columns,
    so each slide is ordered on its own before the next one below it.
    """
    heights = sorted(block.bottom - block.top for block in blocks if block.kind == "text")
    if not heights:
        return [blocks]
    threshold = max(_MIN_UNIT_GAP, heights[len(heights) // 2] * _UNIT_GAP_LINES)
    units: list[list[_Block]] = []
    reach = float("-inf")
    for block in sorted(blocks, key=lambda block: block.top):
        if not units or block.top - reach >= threshold:
            units.append([])
        units[-1].append(block)
        reach = max(reach, block.bottom)
    return units


def _read_columns(left: list[_Block], right: list[_Block], spans: list[_Block]) -> list[_Block]:
    ordered: list[_Block] = []
    cursor = float("-inf")
    for span in sorted(spans, key=lambda block: block.top):
        ordered.extend(_band(left, right, cursor, span.top))
        ordered.append(span)
        cursor = span.top
    ordered.extend(_band(left, right, cursor, float("inf")))
    return ordered


def _band(left: list[_Block], right: list[_Block], start: float, end: float) -> list[_Block]:
    return _order_region([block for block in left if start <= block.top < end]) + _order_region(
        [block for block in right if start <= block.top < end]
    )


def _partition(blocks: list[_Block], gutter: tuple[float, float]) -> tuple[list[_Block], list[_Block], list[_Block]]:
    gap_x0, gap_x1 = gutter
    middle = (gap_x0 + gap_x1) / 2
    left: list[_Block] = []
    right: list[_Block] = []
    spans: list[_Block] = []
    for block in blocks:
        if block.x0 < gap_x0 and block.x1 > gap_x1:
            spans.append(block)
        elif (block.x0 + block.x1) / 2 < middle:
            left.append(block)
        else:
            right.append(block)
    return left, right, spans


def _find_gutter(blocks: list[_Block]) -> tuple[float, float] | None:
    """Return the clearest vertical gap that separates two columns.

    A table inside one column counts as that column's content. A picture
    does not, since a figure set beside its paragraph belongs with it.
    """
    content = [block for block in blocks if block.kind != "image"]
    if len(content) < _MIN_SIDE * 2:
        return None
    content_left = min(block.x0 for block in content)
    content_right = max(block.x1 for block in content)
    content_width = content_right - content_left
    if content_width < _MIN_GUTTER * 3:
        return None
    content_middle = (content_left + content_right) / 2
    narrow = [
        block
        for block in content
        if _MIN_GUTTER * 2 <= block.x1 - block.x0 <= content_width * 0.7
        and abs((block.x0 + block.x1) / 2 - content_middle) > content_width * 0.04
    ]
    if len(narrow) < _MIN_SIDE * 2:
        return None

    best: tuple[float, float, float] | None = None
    gap_start: float | None = None
    step = 2
    allowed = len(narrow) // _GUTTER_CROSSINGS
    x = content_left
    while x <= content_right:
        covered = sum(1 for block in narrow if block.x0 <= x <= block.x1) > allowed
        if not covered:
            if gap_start is None:
                gap_start = x
        elif gap_start is not None:
            best = _wider_gap(best, gap_start, x)
            gap_start = None
        x += step
    if best is None:
        return None
    _, gap_x0, gap_x1 = best
    if gap_x0 <= content_left + step or gap_x1 >= content_right - step:
        return None

    middle = (gap_x0 + gap_x1) / 2
    left = [block for block in narrow if (block.x0 + block.x1) / 2 < middle]
    right = [block for block in narrow if (block.x0 + block.x1) / 2 >= middle]
    if len(left) < _MIN_SIDE or len(right) < _MIN_SIDE:
        return None
    if _side_chars(left) < _MIN_SIDE_CHARS or _side_chars(right) < _MIN_SIDE_CHARS:
        return None
    wide_gap = gap_x1 - gap_x0 >= _MIN_GUTTER * 3
    for side in (left, right):
        if _median_width(side) < _MIN_LINE_WIDTH and not (wide_gap and _is_grid(side)):
            return None
    overlap = min(max(block.bottom for block in left), max(block.bottom for block in right)) - max(
        min(block.top for block in left), min(block.top for block in right)
    )
    if overlap < _MIN_OVERLAP:
        return None
    return gap_x0, gap_x1


def _is_grid(blocks: list[_Block]) -> bool:
    """Short cells starting at three or more column positions, as in a table on a slide."""
    starts = {round(block.x0 / _MIN_GUTTER) for block in blocks}
    return len(starts) >= 3


def _side_chars(blocks: list[_Block]) -> int:
    total = 0
    for block in blocks:
        payload = block.payload
        if block.kind != "text":
            total += _MIN_SIDE_CHARS
        elif isinstance(payload, dict):
            total += len(str(payload.get("text") or ""))
    return total


def _median_width(blocks: list[_Block]) -> float:
    widths = sorted(block.x1 - block.x0 for block in blocks)
    return widths[len(widths) // 2]


def _wider_gap(best: tuple[float, float, float] | None, start: float, end: float):
    width = end - start
    if width < _MIN_GUTTER or (best is not None and width <= best[0]):
        return best
    return width, start, end


def _image_box(image) -> tuple[float, float, float, float] | None:
    x0 = float(image["x0"])
    top = float(image["top"])
    x1 = float(image["x1"])
    bottom = float(image["bottom"])
    if x1 < x0:
        x0, x1 = x1, x0
    if bottom < top:
        top, bottom = bottom, top
    if x1 - x0 < 1 or bottom - top < 1:
        return None
    return x0, top, x1, bottom


def _outside_tables(words, boxes) -> list[dict]:
    kept = []
    for word in words:
        if not word.get("text"):
            continue
        center_x = (word["x0"] + word["x1"]) / 2
        center_y = (word["top"] + word["bottom"]) / 2
        if any(
            x0 <= center_x <= x1 and top <= center_y <= bottom
            for x0, top, x1, bottom in boxes
        ):
            continue
        kept.append(word)
    return kept


def _lines(words: list[dict]) -> list[dict]:
    """Group words into visual lines.

    Words are first gathered into bands by vertical overlap, so a full-width
    glyph or a subscript with a different box still sits on the line of the
    letters beside it. Each band is then split where a horizontal gap is
    wider than a word space, so two columns on the same baseline stay apart.
    A bullet glyph or a paragraph number set apart in the margin then joins
    the line beside it.
    """
    ordered = sorted(words, key=lambda word: (word["top"], word["x0"]))
    bands: list[dict] = []
    for word in ordered:
        if bands and _same_band(bands[-1], word):
            bands[-1]["words"].append(word)
            continue
        bands.append({"top": float(word["top"]), "bottom": _word_bottom(word), "words": [word]})

    lines: list[dict] = []
    for band in bands:
        for word in sorted(band["words"], key=lambda word: word["x0"]):
            if lines and lines[-1]["band"] is band and _same_line(lines[-1], word):
                lines[-1]["words"].append(word)
                continue
            lines.append({"band": band, "words": [word]})

    for line in lines:
        del line["band"]
        _measure_line(line)
    return _join_labels(lines)


def _measure_line(line: dict, prefix: str = "") -> None:
    line["words"].sort(key=lambda word: word["x0"])
    line["text"] = normalize_inline(prefix + _word_text(line["words"]))
    line["x0"] = min(float(word["x0"]) for word in line["words"])
    line["x1"] = max(float(word["x1"]) for word in line["words"])
    line["size"] = max(float(word.get("size") or 0) for word in line["words"])
    line["bold"] = _line_is_bold(line["words"])
    line["bottom"] = max(word.get("bottom", word["top"] + line["size"]) for word in line["words"])
    line["top"] = min(word["top"] for word in line["words"])


def _word_text(words: list[dict]) -> str:
    """Join words with spaces, but not where a font change split one word.

    Letters set touching run on as one word, and so does a comma or closing
    bracket touching the word before it, or an opening bracket touching the
    word after it, as in a bold word followed by a plain comma.
    """
    parts: list[str] = []
    previous = None
    for word in words:
        if previous is not None:
            size = max(float(word.get("size") or 0), float(previous.get("size") or 0))
            gap = float(word["x0"]) - float(previous["x1"])
            last, first = previous["text"][-1:], word["text"][:1]
            touching = (
                (last.isalpha() and first.isalpha())
                or first in _CLOSING_MARKS
                or last in _OPENING_MARKS
                or (last.isalnum() and first in "([")
            )
            parts.append("" if touching and gap < size * _TIGHT_JOIN else " ")
        parts.append(word["text"])
        previous = word
    return "".join(parts)


def _join_labels(lines: list[dict]) -> list[dict]:
    """Join a lone bullet glyph or margin number to the text on its right."""
    pairs: dict[int, int] = {}
    for index, line in enumerate(lines):
        if _label_kind(line) is None:
            continue
        target = _label_target(lines, index, set(pairs.values()))
        if target is not None:
            pairs[index] = target
    if not pairs:
        return lines
    for index, target in pairs.items():
        label = lines[index]
        body = lines[target]
        if _label_kind(label) == "number":
            prefix = f"{label['text']} "
            body["side_label"] = True
        else:
            prefix = "• "
        _measure_line(body, prefix)
        body["x0"] = float(label["x0"])
    return [line for index, line in enumerate(lines) if index not in pairs]


def _label_kind(line: dict) -> str | None:
    if len(line["words"]) != 1:
        return None
    text = line["text"]
    if text in _MARKER_GLYPHS and text != "§":
        return "bullet"
    if text in _LETTER_BULLETS:
        return "bullet"
    if _SIDE_LABEL.match(text):
        return "number"
    return None


def _label_target(lines: list[dict], index: int, consumed: set[int]) -> int | None:
    """The line a label introduces: the nearest one to its right on the same row.

    A number with text just before it on the row ends that text, as an
    equation number does, and a paragraph number only starts a sentence.
    """
    label = lines[index]
    numbered = _label_kind(label) == "number"
    center = (float(label["top"]) + float(label["bottom"])) / 2
    best: tuple[float, int] | None = None
    for other_index, other in enumerate(lines):
        if other_index == index or not float(other["top"]) - 1 <= center <= float(other["bottom"]) + 1:
            continue
        before = float(label["x0"]) - float(other["x1"])
        if numbered and 0 <= before <= _MAX_LABEL_GAP:
            return None
        if other_index in consumed or _label_kind(other) is not None:
            continue
        gap = float(other["x0"]) - float(label["x1"])
        if gap < 0 or gap > _MAX_LABEL_GAP:
            continue
        if numbered and not (other["text"][:1].isupper() or other["text"][:1].isdigit()):
            continue
        if best is None or gap < best[0]:
            best = (gap, other_index)
    return None if best is None else best[1]


def _same_band(band: dict, word: dict) -> bool:
    """A word joins the band when its center sits inside it, or the band's center sits in the word."""
    top, bottom = float(band["top"]), float(band["bottom"])
    word_top, word_bottom = float(word["top"]), _word_bottom(word)
    center = (word_top + word_bottom) / 2
    band_center = (top + bottom) / 2
    if top <= center <= bottom or word_top <= band_center <= word_bottom:
        return True
    return abs(word_top - top) <= 3


def _same_line(line: dict, word: dict) -> bool:
    right = max(float(item["x1"]) for item in line["words"])
    return float(word["x0"]) - right <= _MAX_WORD_GAP


def _word_bottom(word: dict) -> float:
    bottom = word.get("bottom")
    if bottom is None:
        return float(word["top"]) + float(word.get("size") or 0)
    return float(bottom)


def _join_wrapped(lines: list[str]) -> str:
    """Join visual lines, keeping a hyphen that splits one word."""
    joined = ""
    for line in lines:
        if not line:
            continue
        if not joined:
            joined = line
            continue
        if (
            joined.endswith("-")
            and not joined.endswith("--")
            and joined[-2:-1].isalpha()
            and line[:1].isalnum()
        ):
            joined = f"{joined}{line}"
        else:
            joined = f"{joined} {line}"
    return joined


def _take_figure_lead(sections: list[Section], state: HeadingState, page_number: int) -> str:
    if not sections:
        return ""
    previous = sections[-1]
    if previous.kind != "text" or previous.page != page_number:
        return ""
    if previous.headings != list(state.headings):
        return ""
    text = previous.data.strip()
    if len(text) > _FIGURE_CAPTION_LIMIT or _FIGURE.match(text) is None:
        return ""
    sections.pop()
    return text


def _following_caption(
    items: list[_Block],
    index: int,
    body_size: float,
    height: float,
    chrome: dict[str, float],
    outlines: dict[str, int],
    repeats: set[str],
) -> tuple[str, int]:
    """Return a short caption sitting under this image, and how many blocks it used."""
    image = items[index]
    lines: list[str] = []
    previous_bottom = image.bottom
    line_gap: float | None = None
    cursor = index + 1
    while cursor < len(items) and items[cursor].kind == "text":
        payload = items[cursor].payload
        if not isinstance(payload, dict):
            break
        text = payload["text"]
        gap = float(payload["top"]) - previous_bottom
        if not text or _skips_caption(payload, body_size, height, chrome, gap, outlines, repeats):
            break
        size = float(payload["size"])
        if not lines:
            if gap > max(size * 2.5, 28):
                break
        elif _starts_paragraph(gap, size, line_gap):
            break
        elif line_gap is None and gap > 0:
            line_gap = gap
        lines.append(text)
        previous_bottom = float(payload["bottom"])
        cursor += 1
    joined = _join_wrapped(lines)
    limit = _FIGURE_CAPTION_LIMIT if _FIGURE.match(joined) else _CAPTION_LIMIT
    if not joined or len(joined) > limit:
        return "", 0
    return joined, len(lines)


def _skips_caption(
    line: dict,
    body_size: float,
    height: float,
    chrome: dict[str, float],
    gap: float,
    outlines: dict[str, int],
    repeats: set[str],
) -> bool:
    text = line["text"]
    if _is_margin_chrome(line, height, chrome):
        return True
    if _is_page_number(line, body_size) and _in_margin(line["top"], line["bottom"], height):
        return True
    if _is_running_title(line, height, repeats):
        return True
    if _TOC_LINE.search(text):
        return True
    if _qualifies(line, body_size, gap, outlines):
        return True
    if TABLE_LABEL.match(text) is not None:
        return True
    return _BULLET.match(text) is not None or _NUMBERED.match(text) is not None


def _starts_paragraph(gap: float, size: float, line_gap: float | None) -> bool:
    """Return whether ``gap`` is a paragraph break rather than line spacing.

    The gap is the space between the ink of one line and the next. Wrapped
    lines sit about a leading apart. A new paragraph leaves a larger gap.
    Once a paragraph has a measured line gap, a break has to clear that gap.
    """
    if line_gap is not None:
        return gap > line_gap + max(size * 0.5, 4)
    return gap > max(size, 1)


def _margin_chrome(pages: list[tuple[int, float, tuple]]) -> dict[str, float]:
    """Return margin text repeated on many pages, with the size it is usually set in.

    The same words set much larger, such as a product name that is both the
    running header and the first page's title, are not chrome.
    """
    if len(pages) < 3:
        return {}
    counts: Counter[str] = Counter()
    sizes: dict[str, list[float]] = {}
    for _, height, (words, tables, _) in pages:
        seen: set[str] = set()
        for line in _lines(words):
            if not line["text"] or not _in_margin(line["top"], line["bottom"], height):
                continue
            norm = _chrome_key(line["text"])
            if len(norm) >= 4:
                seen.add(norm)
                sizes.setdefault(norm, []).append(float(line["size"]))
        for bbox, kind, rendered in tables:
            if kind != "table" or not isinstance(rendered, str):
                continue
            if not _in_margin(bbox[1], bbox[3], height):
                continue
            norm = _norm_chrome(rendered)
            if len(norm) >= 4:
                seen.add(norm)
        counts.update(seen)
    threshold = max(3, math.ceil(len(pages) * _CHROME_SHARE))
    return {
        text: median(sizes[text]) if text in sizes else math.inf
        for text, count in counts.items()
        if count >= threshold
    }


def _without_chrome_tables(tables, height: float, chrome: dict[str, float]):
    kept = []
    for bbox, kind, rendered in tables:
        if (
            kind == "table"
            and isinstance(rendered, str)
            and _in_margin(bbox[1], bbox[3], height)
            and _norm_chrome(rendered) in chrome
        ):
            continue
        kept.append((bbox, kind, rendered))
    return kept


def _is_margin_chrome(line: dict, height: float, chrome: dict[str, float]) -> bool:
    if not chrome or not _in_margin(line["top"], line["bottom"], height):
        return False
    usual = chrome.get(_chrome_key(line["text"]))
    return usual is not None and float(line["size"]) <= usual + _CHROME_SIZE_SLACK


def _in_margin(top: float, bottom: float, height: float) -> bool:
    if height <= 0:
        return False
    center = (top + bottom) / 2
    return center < height * 0.10 or center > height * 0.90


def _norm_chrome(text: str) -> str:
    return re.sub(r"\d+", "#", normalize_inline(text).lower())


def _chrome_key(text: str) -> str:
    """A margin line's opening words, so a page number that joins the line on some pages still matches."""
    return _norm_chrome(text)[:_CHROME_PREFIX]


def _is_page_number(line: dict, body_size: float) -> bool:
    """Return whether this line is only a page number set near body size."""
    return bool(_PAGE_NUMBER.match(line["text"])) and line["size"] <= body_size * 1.5


def _body_size(pages: list[tuple[int, float, tuple]]) -> float:
    """Median size of the words that are not bold. Bold headings do not set it."""
    plain: list[float] = []
    every: list[float] = []
    for _, _, (words, _, _) in pages:
        for word in words:
            if not word.get("size"):
                continue
            size = float(word["size"])
            every.append(size)
            if not _font_is_bold(word.get("fontname") or ""):
                plain.append(size)
    sizes = plain or every
    if not sizes:
        return 0.0
    return float(median(sizes))


def _outline_levels(pdf) -> dict[str, int]:
    """Map each outline title to its level. The first entry for a title wins.

    An entry with no words, such as a bare ``1.1.1`` bookmark on a numbered
    paragraph, names no section and is left out.
    """
    found: dict[str, int] = {}
    try:
        entries = pdf.doc.get_outlines()
    except (PDFNoOutlines, PDFSyntaxError, PSEOF, ValueError, KeyError):
        return found
    for level, title, *_rest in entries:
        text = normalize_inline(str(title))
        if sum(char.isalpha() for char in text) < 2:
            continue
        found.setdefault(text.casefold(), max(int(level), 1))
    return found


def _running_titles(pages: list[tuple[int, float, tuple]]) -> set[str]:
    """Short titles repeated in the top or bottom band of most pages."""
    if len(pages) < 3:
        return set()
    counts: Counter[str] = Counter()
    for _, height, (words, _, _) in pages:
        seen: set[str] = set()
        for line in _lines(words):
            if not line["text"] or not _in_running_band(line, height):
                continue
            if not looks_like_heading(line["text"]):
                continue
            seen.add(_norm_title(line["text"]))
        counts.update(seen)
    threshold = max(3, (len(pages) * 3 + 4) // 5)
    return {text for text, count in counts.items() if count >= threshold}


def _heading_scale(candidates: list[dict], body_size: float) -> dict[float, int]:
    """Rank distinct heading sizes. The largest size is level 1."""
    found = [_size_key(line["size"]) for line in candidates if line["size"] >= body_size * 1.08]
    ranked = sorted(set(found), reverse=True)
    return {size: min(index + 1, 6) for index, size in enumerate(ranked)}


def _outlines_under_cover(candidates: list[dict], body_size: float, outlines: dict[str, int]) -> dict[str, int]:
    """Move every outline entry one level down when a larger title opens the file above them.

    A bookmark tree starts at level 1 with the first section it names. A
    cover title set larger than any bookmarked heading, before the first of
    them, is the document's title and sits above that tree, so the tree's
    levels each move down one. The sized levels are ranked from the same
    sizes, so they already agree.
    """
    if not outlines:
        return outlines
    positions = [
        index for index, line in enumerate(candidates) if _outline_level(line["text"], outlines) is not None
    ]
    if not positions:
        return outlines
    first = positions[0]
    largest = max(float(candidates[index]["size"]) for index in positions)
    cover = [
        line
        for line in candidates[:first]
        if float(line["size"]) > largest + 0.5 and float(line["size"]) >= body_size * _TITLE_SCALE
    ]
    if not cover:
        return outlines
    return {text: min(level + 1, 6) for text, level in outlines.items()}


def _heading_candidates(
    pages: list[tuple[int, float, tuple]],
    body_size: float,
    chrome: dict[str, float],
    repeats: set[str],
    outlines: dict[str, int],
) -> list[dict]:
    """Every line that qualifies as a title, in reading order, with its size and weight."""
    found: list[dict] = []
    for _, height, (words, tables, images) in pages:
        visible = _without_chrome_tables(tables, height, chrome)
        items = _ordered_blocks(words, visible, images)
        index = 0
        previous_bottom: float | None = None
        while index < len(items):
            block = items[index]
            if block.kind != "text" or not isinstance(block.payload, dict):
                previous_bottom = None
                index += 1
                continue
            line = block.payload
            if _ignored_line(line, height, chrome, repeats, body_size):
                index += 1
                continue
            if previous_bottom is not None and line["top"] + 2 < previous_bottom:
                previous_bottom = None
            matched = _candidate_heading(
                items, index, previous_bottom, body_size, height, chrome, repeats, outlines
            )
            if matched is not None:
                merged, count = matched
                found.append(merged)
                previous_bottom = merged["bottom"]
                index += count
                continue
            previous_bottom = float(line["bottom"])
            index += 1
    return found


def _candidate_heading(
    items: list[_Block],
    index: int,
    previous_bottom: float | None,
    body_size: float,
    height: float,
    chrome: dict[str, float],
    repeats: set[str],
    outlines: dict[str, int],
) -> tuple[dict, int] | None:
    """Join wrapped lines of one title and return it when the title qualifies."""
    block = items[index]
    if block.kind != "text" or not isinstance(block.payload, dict):
        return None
    first = block.payload
    if _ignored_line(first, height, chrome, repeats, body_size):
        return None
    parts = [first]
    cursor = index + 1
    while cursor < len(items) and len(parts) < 3:
        nxt_block = items[cursor]
        if nxt_block.kind != "text" or not isinstance(nxt_block.payload, dict):
            break
        nxt = nxt_block.payload
        if _ignored_line(nxt, height, chrome, repeats, body_size):
            break
        gap = float(nxt["top"]) - float(parts[-1]["bottom"])
        if not _continues_heading(parts[-1], nxt, gap, body_size):
            break
        parts.append(nxt)
        cursor += 1
    while parts:
        merged = _merge_lines(parts)
        gap_above = None if previous_bottom is None else float(parts[0]["top"]) - previous_bottom
        cursor = index + len(parts)
        if _qualifies(merged, body_size, gap_above, outlines) or _is_bold_title(
            merged, gap_above, items, cursor, body_size
        ):
            if _is_byline(merged, items, index, len(parts)):
                return None
            if _runs_into_prose(merged, items, cursor, body_size):
                return None
            return merged, len(parts)
        if len(parts) == 1:
            return None
        parts.pop()
    return None


def _is_byline(line: dict, items: list[_Block], index: int, count: int) -> bool:
    """A line of author names under a larger title, which an email address follows.

    Names are set larger than the body under a paper's title, but they head
    nothing. A line counts as names when every word is capitalized or a name
    particle, a larger line sits above it, and an email address appears on
    it or on the next few lines.
    """
    text = line["text"]
    words = text.replace(",", " ").split()
    if not 2 <= len(words) <= 12 or _BYLINE_STOP.search(text):
        return False
    if not all(_NAME_WORD.match(word) for word in words):
        return False
    above = [
        block.payload
        for block in items[:index]
        if block.kind == "text" and isinstance(block.payload, dict) and block.bottom <= line["top"]
    ]
    if not any(float(other["size"]) > float(line["size"]) + 0.5 for other in above):
        return False
    following = [text]
    start = index + count
    for block in items[start : start + _BYLINE_LOOKAHEAD]:
        if block.kind != "text" or not isinstance(block.payload, dict):
            break
        following.append(block.payload["text"])
    return any(_EMAIL_DOMAIN.search(line) for line in following)


def _is_bold_title(
    line: dict, gap: float | None, items: list[_Block], cursor: int, body_size: float
) -> bool:
    """A short bold line at body size, with space above and plain text below, heads a section.

    Handbooks and policies often set their titles this way.
    """
    text = line["text"]
    if not line["bold"] or body_size <= 0 or float(line["size"]) < body_size - 0.5:
        return False
    if len(text.split()) > _BOLD_TITLE_WORDS or not looks_like_heading(text):
        return False
    if _FIGURE.match(text) or TABLE_LABEL.match(text):
        return False
    if not _title_cased(text):
        return False
    if not _isolated(gap, float(line["size"])) or cursor >= len(items):
        return False
    block = items[cursor]
    if block.kind != "text" or not isinstance(block.payload, dict):
        return False
    nxt = block.payload
    return not nxt["bold"] and nxt["text"][:1].isalnum() and float(nxt["top"]) > float(line["top"])


def _title_cased(text: str) -> bool:
    """A title's later words start with a capital, a digit, or are a small word.

    A bold sentence such as ``Bring the package`` stays in the body. A
    handbook title such as ``Smoking, Alcohol and Drugs`` does not.
    """
    words = re.findall(r"[A-Za-z0-9][\w'’-]*", text)
    return bool(words) and all(
        word.lower() in _SMALL_WORDS or word[:1].isupper() or word[:1].isdigit() for word in words[1:]
    )


def _runs_into_prose(line: dict, items: list[_Block], cursor: int, body_size: float) -> bool:
    """A plain line whose sentence goes on in lowercase just below opens a paragraph.

    On a page set larger than the rest of the file, its first line would
    otherwise pass as a title.
    """
    if line["bold"] or line["size"] >= body_size * _TITLE_SCALE or cursor >= len(items):
        return False
    block = items[cursor]
    if block.kind != "text" or not isinstance(block.payload, dict):
        return False
    nxt = block.payload
    gap = float(nxt["top"]) - float(line["bottom"])
    return (
        gap <= float(line["size"]) * 0.5
        and abs(float(nxt["size"]) - float(line["size"])) <= 0.6
        and not nxt["bold"]
        and nxt["text"][:1].islower()
    )


def _continues_heading(previous: dict, nxt: dict, gap: float, body_size: float) -> bool:
    """A wrapped title continues in the same font, close underneath, in lowercase.

    A title set well above body size is a document title, which wraps in
    title case and is often centered. Its next line continues it when the
    two share a left edge or a center, unless that line starts a new
    numbered or chapter heading.
    """
    if gap > max(float(previous["size"]) * 0.5, 5):
        return False
    if abs(float(nxt["size"]) - float(previous["size"])) > 0.6:
        return False
    if bool(nxt["bold"]) != bool(previous["bold"]):
        return False
    title = body_size > 0 and float(previous["size"]) >= body_size * _TITLE_SCALE
    if abs(float(nxt["x0"]) - float(previous["x0"])) > 12 and not (
        title and abs(_center(nxt) - _center(previous)) <= 12
    ):
        return False
    if previous["text"].endswith((".", ",", ";", ":", "!", "?", "-")):
        return False
    if nxt["text"][:1].isupper() and looks_like_heading(nxt["text"]):
        if not title or _starts_new_heading(previous["text"]) or _starts_new_heading(nxt["text"]):
            return False
    return len(_join_wrapped([previous["text"], nxt["text"]])) <= 100


def _center(line: dict) -> float:
    return (float(line["x0"]) + float(line["x1"])) / 2


def _starts_new_heading(text: str) -> bool:
    return bool(_CHAPTER.match(text) or _NUMBERED_TITLE.match(text) or _SECTION_NUMBER.match(text))


def _merge_lines(parts: list[dict]) -> dict:
    return {
        "text": _join_wrapped([part["text"] for part in parts]),
        "size": max(float(part["size"]) for part in parts),
        "bold": all(part["bold"] for part in parts),
        "top": float(parts[0]["top"]),
        "bottom": float(parts[-1]["bottom"]),
        "last_top": float(parts[-1]["top"]),
        "x0": float(parts[0]["x0"]),
        "side_label": any(part.get("side_label") for part in parts),
    }


def _qualifies(line: dict, body_size: float, gap: float | None, outlines: dict[str, int]) -> bool:
    """A title is larger than the body, or a section pattern, or an outline entry.

    A numbered line such as ``1. Mounting Position`` is a list item unless it
    is set in bold, when it is a numbered section title. A number set apart
    in the margin labels a paragraph, so it only makes a title in bold. A
    ``Table N`` or ``Figure N`` line is a caption, not a title. A line only a
    little larger than the body with fewer than four letters, such as a
    ``Cp`` or ``P0!`` label on a diagram, is not a title either unless it is
    set in bold.
    """
    text = line["text"]
    if body_size <= 0 or _FIGURE.match(text) or TABLE_LABEL.match(text):
        return False
    numbered = _NUMBERED_TITLE.match(text) is not None
    if numbered and not line["bold"]:
        return False
    if line.get("side_label") and not line["bold"] and line["size"] < body_size * 1.08:
        return False
    if _outline_level(text, outlines) is not None and len(text) <= 200 and not text.endswith("."):
        return True
    if not looks_like_heading(text):
        return False
    larger = line["size"] >= body_size + 0.6 and line["size"] >= body_size * 1.08
    strong = line["size"] >= body_size * 1.25
    patterned = _pattern_level(text) is not None
    if strong:
        return True
    if _few_letters(text) and not line["bold"]:
        return False
    if larger and (line["bold"] or _isolated(gap, line["size"]) or patterned):
        return True
    if patterned and (line["bold"] or _isolated(gap, line["size"])):
        return True
    return False


def _few_letters(text: str) -> bool:
    """Fewer than four letters, as in a diagram label such as ``Cp`` or ``P0! P1!``."""
    return sum(1 for char in text if char.isalpha()) < _MIN_TITLE_LETTERS


def _assigned_level(line: dict, body_size: float, scale: dict[float, int], outlines: dict[str, int]) -> int:
    outlined = _outline_level(line["text"], outlines)
    if outlined is not None:
        return outlined
    sized = _scale_level(line["size"], scale, body_size)
    if sized is not None:
        return sized
    numbered = _NUMBERED_TITLE.match(line["text"])
    if numbered is not None and scale:
        # A bold numbered title at body size sits under every sized heading.
        return min(max(scale.values()) + 1 + numbered.group(1).count("-"), 6)
    pattern = _pattern_level(line["text"])
    if pattern is not None:
        return pattern
    if scale:
        return min(max(scale.values()) + 1, 6)
    return 1


def _consistent_level(state: HeadingState, text: str, level: int) -> int:
    """Keep a numbered title in line with the numbered titles already open.

    ``4-1`` belongs under ``4``. When the open title at that depth is ``3``,
    the document skipped its ``4`` title, so ``4-1`` takes the place of ``3``
    rather than nesting under it. A title numbered like an open sibling takes
    that sibling's level.
    """
    number = _heading_number(text)
    if number is None or len(number) < 2:
        return level
    parent = number[:-1]
    for open_level, title in reversed(list(zip(state.levels, state.headings, strict=True))):
        open_number = _heading_number(title)
        if open_number is None:
            continue
        if open_number == parent:
            return level
        if len(open_number) == len(number) or len(open_number) == len(parent):
            return open_level
    return level


def _heading_number(text: str) -> tuple[str, ...] | None:
    match = _MULTINUM.match(text)
    if match is not None:
        return tuple(match.group(1).split("."))
    match = _NUMBERED_TITLE.match(text)
    if match is not None:
        return tuple(match.group(1).split("-"))
    return None


def _scale_level(size: float, scale: dict[float, int], body_size: float) -> int | None:
    if not scale or size < body_size * 1.08:
        return None
    key = _size_key(size)
    if key in scale:
        return scale[key]
    nearest = min(scale, key=lambda item: abs(item - key))
    if abs(nearest - key) <= 0.5:
        return scale[nearest]
    return None


def _pattern_level(text: str) -> int | None:
    if not looks_like_heading(text) or len(text.split()) > 12:
        return None
    if _CHAPTER.match(text):
        return 1
    if _SECTION_WORD.match(text):
        return 2
    match = _MULTINUM.match(text)
    if match is not None:
        return min(match.group(1).count(".") + 1, 6)
    match = _NUMBERED_TITLE.match(text)
    if match is None:
        return None
    return min(match.group(1).count("-") + 2, 6)


def _outline_level(text: str, outlines: dict[str, int]) -> int | None:
    return outlines.get(normalize_inline(text).casefold())


def _isolated(gap: float | None, size: float) -> bool:
    """The first line on a page, or a line with more space above than body leading."""
    if gap is None:
        return True
    return gap >= max(size * 0.55, 6)


def _size_key(size: float) -> float:
    return round(float(size) * 2) / 2


def _ignored_line(line: dict, height: float, chrome: dict[str, float], repeats: set[str], body_size: float) -> bool:
    if not line.get("text"):
        return True
    if _is_margin_chrome(line, height, chrome):
        return True
    if _is_page_number(line, body_size) and _in_margin(line["top"], line["bottom"], height):
        return True
    if _TOC_LINE.search(line["text"]):
        return True
    return _is_running_title(line, height, repeats)


def _is_running_title(line: dict, height: float, repeats: set[str]) -> bool:
    if not repeats or not _in_running_band(line, height):
        return False
    return _norm_title(line["text"]) in repeats


def _in_running_band(line: dict, height: float) -> bool:
    if height <= 0:
        return False
    center = (float(line["top"]) + float(line["bottom"])) / 2
    return center < height * 0.18 or center > height * 0.88


def _norm_title(text: str) -> str:
    return normalize_inline(text).casefold()


def _line_is_bold(words: list[dict]) -> bool:
    letters = 0
    bold_letters = 0
    for word in words:
        count = sum(1 for char in word.get("text") or "" if char.isalpha())
        if count == 0:
            continue
        letters += count
        if _font_is_bold(word.get("fontname") or ""):
            bold_letters += count
    if letters == 0:
        return False
    return bold_letters / letters >= 0.75


def _font_is_bold(name: str) -> bool:
    return _BOLD_FONT.search(name) is not None
