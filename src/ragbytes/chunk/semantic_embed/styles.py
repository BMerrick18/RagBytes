"""Named semantic chunking styles, and the limits each one cuts by."""

import statistics
from dataclasses import dataclass, replace
from typing import Literal

StyleName = Literal["precise", "balanced", "broad"]

# A document needs this many neighbour scores before its own spread is trusted
# to move the floor. A shorter document keeps the style's floor.
_ADAPT_PAIRS = 20
# A document whose passages score high may raise the floor, but only by this
# much, so precise, balanced, and broad stay apart.
_FLOOR_RAISE = 0.04


@dataclass(frozen=True)
class Style:
    """How readily semantic chunking cuts, and how large a chunk may grow.

    ``floor`` is the score below which neighbours are unrelated. A long enough
    document moves it with that document's own scores, down as far as
    ``floor_low`` or up by a small step, and never above the document's
    median. ``min_chars`` and ``max_chars`` bound a chunk's size. A text run
    under ``fragment_chars`` that does not end like a sentence, such as a date
    or a label, always joins a neighbour, and so does any text run under
    ``tiny_chars``, half the minimum, whatever its score. ``merge_headings``
    lets small neighbouring headings share a chunk.
    """

    name: StyleName
    floor: float
    floor_low: float
    min_chars: int
    max_chars: int
    fragment_chars: int = 40
    merge_headings: bool = True

    @property
    def tiny_chars(self) -> int:
        """Text this short cannot stand as a chunk, however unrelated its neighbours score."""
        return self.min_chars // 2


STYLES: dict[StyleName, Style] = {
    "precise": Style("precise", floor=0.35, floor_low=0.25, min_chars=100, max_chars=1200),
    "balanced": Style("balanced", floor=0.3, floor_low=0.2, min_chars=200, max_chars=2000),
    "broad": Style("broad", floor=0.2, floor_low=0.15, min_chars=400, max_chars=3000),
}
BALANCED = STYLES["balanced"]


def resolve_style(
    name: StyleName = "balanced", *, strict_headings: bool = False, max_chars: int | None = None
) -> Style:
    """Return a named style with the caller's overrides applied.

    A smaller ``max_chars`` also lowers the minimum, so the two never meet.
    """
    style = STYLES[name]
    if max_chars is not None:
        style = replace(style, max_chars=max_chars, min_chars=min(style.min_chars, max_chars // 4))
    if strict_headings:
        style = replace(style, merge_headings=False)
    return style


def for_document(style: Style, neighbour_scores: list[float]) -> Style:
    """Return ``style`` with its floor moved for this document's own scores.

    The floor drops to half a standard deviation below the median, but no
    lower than ``floor_low``. When the passages score high and tight, it
    rises toward one and a half standard deviations below the median, by no
    more than a small step above the style's own floor, and never above the
    median. A wide spread leaves the style floor where it is, so a typical
    document does not start cutting every join.
    """
    if len(neighbour_scores) < _ADAPT_PAIRS:
        return style
    median = statistics.median(neighbour_scores)
    spread = statistics.pstdev(neighbour_scores)
    lowered = median - 0.5 * spread
    if lowered < style.floor:
        return replace(style, floor=min(style.floor, max(style.floor_low, lowered)))
    upper = median - 1.5 * spread
    if upper <= style.floor:
        return style
    cap = min(median, style.floor + _FLOOR_RAISE)
    return replace(style, floor=max(style.floor, min(upper, cap)))
