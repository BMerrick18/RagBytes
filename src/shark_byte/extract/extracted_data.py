"""Sections kept after a file has been extracted."""

from shark_byte.schemas import Section


class ExtractedData:
    """One file's sections, split by complexity.

    ``all_sections`` is the full list. ``simple_sections`` and
    ``complex_sections`` are taken from it, in the same order. These stay
    on the backend and are not part of the API response.
    """

    def __init__(self, sections: list[Section]) -> None:
        self.all_sections = list(sections)
        self.simple_sections = [
            section for section in self.all_sections if section.complexity == "simple"
        ]
        self.complex_sections = [
            section for section in self.all_sections if section.complexity == "complex"
        ]
