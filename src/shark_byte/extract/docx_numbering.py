"""List numbers in a Word document, as Word displays them.

Each numbered paragraph points at a list instance and a level. The level's
format says whether it shows a bullet or a number, and its text pattern,
such as ``%1.`` or ``%1.%2``, says how the number is written. Instances
that share one definition continue each other's count, unless an instance
restarts a level, and a level restarts after an item at a shallower level.
"""

from docx.oxml.ns import qn

_UNNUMBERED = frozenset({"bullet", "none", ""})
_ROMAN = (
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
    (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
)


class ListNumbering:
    """Counts list items in document order and returns the marker each one shows."""

    def __init__(self, document) -> None:
        self._instances: dict[str, tuple[str, dict[int, int]]] = {}
        self._levels: dict[tuple[str, int], tuple[str, int, str]] = {}
        self._counts: dict[str, dict[int, int]] = {}
        self._started: set[str] = set()
        try:
            root = document.part.numbering_part.element
        except (KeyError, NotImplementedError, AttributeError):
            return
        for definition in root.iter(qn("w:abstractNum")):
            abstract_id = definition.get(qn("w:abstractNumId")) or ""
            for level in definition.iter(qn("w:lvl")):
                self._levels[(abstract_id, _int(level.get(qn("w:ilvl")), 0))] = _level_format(level)
        for instance in root.iter(qn("w:num")):
            abstract = instance.find(qn("w:abstractNumId"))
            restarts: dict[int, int] = {}
            for override in instance.iter(qn("w:lvlOverride")):
                start = override.find(qn("w:startOverride"))
                if start is not None:
                    restarts[_int(override.get(qn("w:ilvl")), 0)] = _int(start.get(qn("w:val")), 1)
            self._instances[instance.get(qn("w:numId")) or ""] = (
                abstract.get(qn("w:val")) if abstract is not None else "",
                restarts,
            )

    def marker(self, num_id: str | None, level: int) -> str:
        """The marker for the next item of this list at this level, or ``-`` for a bullet."""
        if not num_id or num_id not in self._instances:
            return "-"
        abstract_id, restarts = self._instances[num_id]
        number_format, _start, pattern = self._levels.get((abstract_id, level), ("bullet", 1, ""))
        if number_format in _UNNUMBERED:
            return "-"
        counts = self._counts.setdefault(abstract_id, {})
        if num_id not in self._started:
            self._started.add(num_id)
            for restarted, start in restarts.items():
                counts[restarted] = start - 1
        for deeper in [key for key in counts if key > level]:
            del counts[deeper]
        counts[level] = counts.get(level, self._start(abstract_id, level) - 1) + 1
        shown = pattern
        for depth in range(9):
            placeholder = f"%{depth + 1}"
            if placeholder not in shown:
                continue
            depth_format = self._levels.get((abstract_id, depth), ("decimal", 1, ""))[0]
            value = counts.get(depth, self._start(abstract_id, depth))
            shown = shown.replace(placeholder, _format_number(value, depth_format))
        return shown.strip() or "-"

    def _start(self, abstract_id: str, level: int) -> int:
        return self._levels.get((abstract_id, level), ("decimal", 1, ""))[1]


def _level_format(level) -> tuple[str, int, str]:
    number_format = level.find(qn("w:numFmt"))
    start = level.find(qn("w:start"))
    pattern = level.find(qn("w:lvlText"))
    return (
        (number_format.get(qn("w:val")) if number_format is not None else "decimal") or "",
        _int(start.get(qn("w:val")) if start is not None else None, 1),
        (pattern.get(qn("w:val")) if pattern is not None else "") or "",
    )


def _format_number(value: int, number_format: str) -> str:
    if number_format in {"lowerLetter", "upperLetter"} and value > 0:
        letter = chr(ord("a") + (value - 1) % 26) * ((value - 1) // 26 + 1)
        return letter.upper() if number_format == "upperLetter" else letter
    if number_format in {"lowerRoman", "upperRoman"} and value > 0:
        roman = _roman(value)
        return roman.upper() if number_format == "upperRoman" else roman
    if number_format == "decimalZero":
        return f"{value:02d}"
    return str(value)


def _roman(value: int) -> str:
    parts: list[str] = []
    for amount, letters in _ROMAN:
        while value >= amount:
            parts.append(letters)
            value -= amount
    return "".join(parts)


def _int(raw, default: int) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default
