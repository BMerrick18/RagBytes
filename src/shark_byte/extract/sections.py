"""Build the sections every extractor returns."""

import base64
import binascii
import re

from shark_byte.extract.render import normalize_inline, render_image
from shark_byte.schemas import Section, SectionKind

_DATA_URI = re.compile(
    r"data:(image/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)",
    re.IGNORECASE,
)
_INTRODUCED = frozenset({"list", "table", "chart"})
_TITLE_MARKER = re.compile(r"^[■□●○◆◇▪▫※◎★☆►▶➢➤]+\s*")
TABLE_LABEL = re.compile(r"^(?:table|tbl\.?)\s+\d+\b", re.IGNORECASE)
_LABEL_LIMIT = 160
_PRODUCT_NAME = re.compile(r"^[a-z]+[A-Z0-9]")


class HeadingState:
    """Heading path applied to each following section."""

    def __init__(self) -> None:
        self._path: list[tuple[int, str]] = []

    def apply(self, level: int, text: str) -> None:
        """Set the title at ``level``. A decorative glyph in front of the title is dropped."""
        cleaned = _TITLE_MARKER.sub("", normalize_inline(text))
        if not cleaned:
            return
        level = max(level, 1)
        self._path = [(existing, name) for existing, name in self._path if existing < level]
        self._path.append((level, cleaned))

    @property
    def headings(self) -> list[str]:
        """Titles from the outer heading down to the nearest one."""
        return [name for _, name in self._path]

    @property
    def levels(self) -> list[int]:
        """Level of each title in ``headings``, outer title first."""
        return [level for level, _ in self._path]

    @property
    def heading(self) -> str | None:
        """The current level-1 title, when the path has one."""
        for existing, name in self._path:
            if existing <= 1:
                return name
        return None

    @property
    def subheading(self) -> str | None:
        """The nearest title below level 1."""
        names = [name for existing, name in self._path if existing > 1]
        if not names:
            return None
        return names[-1]


def add_section(
    sections: list[Section],
    kind: SectionKind,
    data: str,
    state: HeadingState,
    *,
    page: int | None = None,
    media: bytes | None = None,
    media_type: str | None = None,
) -> None:
    """Append one section, skipping empty text.

    A text section that ends with a colon is the introduction to a list, table,
    or chart that follows it, so the two stay in one section. A short
    ``Table N`` label before a table is its caption and stays with it too.
    """
    if kind == "code":
        cleaned = data.strip("\n")
    elif kind == "list":
        cleaned = data.strip("\n").rstrip()
    else:
        cleaned = data.strip()
    if kind == "image" and not cleaned.strip():
        cleaned = render_image()
    elif not cleaned.strip():
        return
    if kind in _INTRODUCED:
        cleaned = _with_lead_in(sections, cleaned, state, page, kind)
    if media and not media_type:
        media_type = sniff_image_type(media)
    section = Section(
        kind=kind,
        headings=list(state.headings),
        heading=state.heading,
        subheading=state.subheading,
        page=page,
        data=cleaned,
        media=media,
        media_type=media_type if media else None,
    )
    section._heading_levels = list(state.levels)
    sections.append(section)


def _with_lead_in(
    sections: list[Section],
    data: str,
    state: HeadingState,
    page: int | None,
    kind: SectionKind,
) -> str:
    if not sections:
        return data
    previous = sections[-1]
    if previous.kind != "text" or not _introduces(previous.data, kind):
        return data
    if previous.headings != list(state.headings):
        return data
    if page is not None and previous.page not in {None, page}:
        return data
    sections.pop()
    if hasattr(previous, "_heading_levels"):
        del previous._heading_levels
    return f"{previous.data}\n{data}"


def _introduces(text: str, kind: SectionKind) -> bool:
    if text.endswith(":"):
        return True
    return kind == "table" and len(text) <= _LABEL_LIMIT and TABLE_LABEL.match(text) is not None


def compose_inline(
    pieces: list[tuple[str, str, bytes | None, str | None]],
) -> tuple[str, list[tuple[str, bytes | None, str | None]], bool]:
    """Join text around image markers.

    Image pieces stay in the sentence as ``[Image: ...]`` and are also
    returned on their own, so the picture bytes still have a section.
    ``has_words`` is false when the pieces are only images.
    """
    parts: list[str] = []
    images: list[tuple[str, bytes | None, str | None]] = []
    has_words = False
    for kind, body, media, media_type in pieces:
        if kind == "image":
            if body:
                parts.append(body)
                images.append((body, media, media_type))
            continue
        if body.strip():
            has_words = True
            parts.append(body.strip())
    return " ".join(parts), images, has_words


def assign_indexes(sections: list[Section]) -> list[Section]:
    """Record each section's place in the file. The first section is 0.

    The shallowest heading level in the file becomes level 1, so a document
    that starts at a deeper heading still fills ``heading``.
    """
    _promote_outer_headings(sections)
    for index, section in enumerate(sections):
        section.index = index
    return sections


def looks_like_heading(text: str) -> bool:
    """Return whether this short line can be a title.

    A title can start in lowercase only with a product name such as
    ``xx555`` or ``iPhone``, whose first word also has a digit or a capital.
    """
    if len(text) < 2 or len(text) > 100 or text.endswith((".", ",", ";", ":")):
        return False
    if text[0].islower() and not _PRODUCT_NAME.match(text):
        return False
    if text[0] in "•●▪◦‣-*":
        return False
    return sum(1 for char in text if char.isalpha()) >= 2


def _promote_outer_headings(sections: list[Section]) -> None:
    """Shift heading levels so the file's shallowest title is level 1."""
    paths: list[list[int] | None] = []
    for section in sections:
        paths.append(getattr(section, "_heading_levels", None))
        if hasattr(section, "_heading_levels"):
            del section._heading_levels
    found = [level for path in paths if path for level in path]
    if not found:
        return
    shift = min(found) - 1
    if shift <= 0:
        return
    for section, path in zip(sections, paths, strict=True):
        if not path or len(path) != len(section.headings):
            continue
        heading: str | None = None
        deeper: list[str] = []
        for level, name in zip((level - shift for level in path), section.headings, strict=True):
            if level <= 1 and heading is None:
                heading = name
            elif level > 1:
                deeper.append(name)
        section.heading = heading
        section.subheading = deeper[-1] if deeper else None


def image_from_data_uri(value: str | None) -> tuple[bytes, str] | None:
    """Decode a ``data:image/...;base64,`` URL, or return None."""
    if not value:
        return None
    match = _DATA_URI.search(value.strip())
    if match is None:
        return None
    payload = re.sub(r"\s+", "", match.group(2))
    payload += "=" * (-len(payload) % 4)
    try:
        media = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error):
        return None
    if not media:
        return None
    return media, match.group(1).lower()


def sniff_image_type(data: bytes) -> str:
    """Return an image media type guessed from the leading bytes."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"
