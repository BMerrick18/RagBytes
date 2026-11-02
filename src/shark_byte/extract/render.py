"""Shared text shape produced by every extractor.

A paragraph is one line. A list uses ``- `` items, indented two spaces per
level. An item the file numbers is written ``1.``, ``2.`` and so on instead.
PDF lists always use ``- ``. Tables are GitHub-flavored markdown with no blank line inside the
table. An image is ``[Image]`` or ``[Image: description]``. A chart is
``[Chart]`` or ``[Chart: title]``. When the file stores the plotted values,
those values follow the chart label as a markdown table in the same block.
A complex region is ``[Complex]``. The original leftover cell or figure is
stored beside that marker.

Headings are not written into that text. Each section carries ``headings``,
the path from the outer title to the nearest one. The shallowest heading
level in the file is level 1. ``heading`` is that outer title, and
``subheading`` is the nearest deeper title.
"""

import re
import unicodedata

_KEEP_FORM = frozenset("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻₀₁₂₃₄₅₆₇₈₉₊₋½¼¾")
_TIGHT_OPEN = re.compile(r"(\() (?=\S)")
_TIGHT_CLOSE = re.compile(r"(?<=\S) (\))")
_FILE_NAME = re.compile(
    r"[\w\-. ()]+\.(?:png|jpe?g|gif|bmp|webp|svg|tiff?|emf|wmf|ico)", re.IGNORECASE
)
_UNICODE_HYPHEN = re.compile(r"(?<=\w)\s*[\u2010\u2011]\s*(?=\w)|[\u2010\u2011]")
# Symbol and Wingdings bullets that PDF and Word fonts map into the private use area.
_PRIVATE_BULLETS = frozenset("\uf0b7\uf0a7\uf0a8\uf0d8\uf0e8\uf0fc\uf076\uf06e\uf0d7\uf09f\uf0a2")


def normalize_inline(value: str | None) -> str:
    """Collapse whitespace into a single line and fold compatibility forms.

    Full-width punctuation, half-width katakana marks, and ligatures become
    their plain equivalents, so ``（Ref.）`` reads as ``(Ref.)`` and ``℃`` as
    ``°C``. Superscripts, subscripts, and vulgar fractions keep their shape,
    since ``mm²`` means something different from ``mm2``. A space just inside
    a parenthesis is removed, since a full-width parenthesis is often set as
    its own word. Unicode hyphens become ``-``, and a hyphen set apart from
    the words it joins, as in ``24 ‐ month``, is closed up. Invisible format
    characters such as zero-width spaces and soft hyphens are dropped. A
    private-use symbol-font bullet becomes ``•`` and any other private-use
    glyph is dropped.
    """
    if not value:
        return ""
    kept: list[str] = []
    for char in value:
        if char in _PRIVATE_BULLETS:
            kept.append("•")
            continue
        category = unicodedata.category(char)
        if category == "Co" or (category == "Cf" and char not in "\u200d"):
            continue
        kept.append(char if char in _KEEP_FORM else unicodedata.normalize("NFKC", char))
    folded = _UNICODE_HYPHEN.sub("-", "".join(kept))
    joined = " ".join(folded.replace("\xa0", " ").split())
    return _TIGHT_CLOSE.sub(r"\1", _TIGHT_OPEN.sub(r"\1", joined))


def render_paragraph(text: str) -> str | None:
    """Return a one-line paragraph, or None when the text is empty."""
    cleaned = normalize_inline(text)
    if not cleaned:
        return None
    return cleaned


def render_table(rows: list[list[str]]) -> str | None:
    """Return a markdown table, or None when every cell is empty.

    A column that is empty in every row is a spacer and is left out.
    """
    normalized: list[list[str]] = []
    for row in rows:
        cells = [_escape_cell(cell) for cell in row]
        if any(cells):
            normalized.append(cells)
    if not normalized:
        return None

    width = max(len(row) for row in normalized)
    padded = [row + [""] * (width - len(row)) for row in normalized]
    kept = [index for index in range(width) if any(row[index] for row in padded)]
    padded = [[row[index] for index in kept] for row in padded]
    width = len(kept)
    lines = [
        _format_row(padded[0]),
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    lines.extend(_format_row(row) for row in padded[1:])
    return "\n".join(lines)


def render_image(description: str | None = None) -> str:
    """Return a placeholder for an image that cannot be read as text.

    A description that is only a file name, such as ``dot_green.png``, says
    nothing about the picture and is left out.
    """
    if description and _FILE_NAME.fullmatch(normalize_inline(description)):
        description = None
    return _marker("Image", description)


def render_complex() -> str:
    """Return the marker for a region left unread."""
    return "[Complex]"


def render_chart(
    title: str | None = None,
    rows: list[list[str]] | None = None,
) -> str:
    """Return a chart label, plus a data table when values are available."""
    label = _marker("Chart", title)
    table = render_table(rows or [])
    if table is None:
        return label
    return f"{label}\n{table}"


def join_blocks(blocks: list[str]) -> str:
    """Join non-empty blocks with a blank line between them."""
    kept = [block.strip() for block in blocks if block and block.strip()]
    return "\n\n".join(kept)


def _escape_cell(value: str) -> str:
    return normalize_inline(value).replace("|", "\\|")


def _format_row(row: list[str]) -> str:
    return "| " + " | ".join(row) + " |"


def _marker(kind: str, description: str | None) -> str:
    cleaned = normalize_inline(description).replace("[", "(").replace("]", ")")
    if cleaned:
        return f"[{kind}: {cleaned}]"
    return f"[{kind}]"
