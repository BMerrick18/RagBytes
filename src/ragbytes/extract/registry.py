from collections.abc import Callable

from ragbytes.extract.extractors import (
    extract_docx,
    extract_html,
    extract_markdown,
    extract_pdf,
    extract_text,
)
from ragbytes.schemas import Section

Extractor = Callable[[bytes], list[Section]]

EXTRACTORS: dict[str, Extractor] = {
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".html": extract_html,
    ".htm": extract_html,
    ".md": extract_markdown,
    ".markdown": extract_markdown,
    ".txt": extract_text,
}


def get_extractor(suffix: str) -> Extractor | None:
    """Return the extractor for a filename suffix, if one is registered."""
    return EXTRACTORS.get(suffix.lower())
