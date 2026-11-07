"""Let a heading too small to be a chunk share one with its neighbouring headings."""

from dataclasses import dataclass, field

from ragbytes.chunk.semantic.embed_prep import HeadingPassages, PreparedSentence
from ragbytes.chunk.semantic.styles import BALANCED, Style


@dataclass
class Umbrella:
    """Passages the second pass compares together, under one shared heading path.

    Most umbrellas hold one heading. When small neighbouring headings are
    joined, ``headings`` is the path they share, and each passage keeps the
    path it came from. ``members`` lists each joined heading path in file order.
    """

    headings: list[str]
    heading: str | None
    subheading: str | None
    passages: list[PreparedSentence]
    members: list[list[str]] = field(default_factory=list)


def merge_small_headings(
    scopes: list[HeadingPassages], ready: list[list[PreparedSentence]], style: Style = BALANCED
) -> list[Umbrella]:
    """Join each heading under the style's minimum size to the neighbouring heading beside it.

    Two headings join when either is that small and both sit no more than one
    level below the path they share: siblings, or a parent's opening text and
    its first child. A heading change between two larger headings is still
    always a boundary. A parent's opening text is the start of its own
    subjects, so it waits for its first child rather than joining the heading
    before it. Joining only lets the second pass compare them, so passages
    that are unrelated are still cut apart there. A style that does not merge
    headings keeps every heading as its own umbrella.
    """
    umbrellas: list[Umbrella] = []
    for position, (scope, passages) in enumerate(zip(scopes, ready, strict=True)):
        if not passages:
            continue
        current = umbrellas[-1] if umbrellas else None
        following = scopes[position + 1].headings if position + 1 < len(scopes) else None
        if (
            style.merge_headings
            and current is not None
            and not _opens(scope.headings, following)
            and _joins(current, scope.headings, passages, style.min_chars)
        ):
            _absorb(current, scope, passages)
            continue
        umbrellas.append(
            Umbrella(
                headings=list(scope.headings),
                heading=scope.heading,
                subheading=scope.subheading,
                passages=list(passages),
                members=[list(scope.headings)],
            )
        )
    return umbrellas


def _opens(headings: list[str], following: list[str] | None) -> bool:
    """The next heading sits directly inside this one."""
    return following is not None and len(following) > len(headings) and following[: len(headings)] == headings


def _joins(current: Umbrella, headings: list[str], passages: list[PreparedSentence], min_chars: int) -> bool:
    if _size(current.passages) >= min_chars and _size(passages) >= min_chars:
        return False
    path = _shared(current.headings, headings)
    return all(len(member) <= len(path) + 1 for member in [*current.members, headings])


def _absorb(current: Umbrella, scope: HeadingPassages, passages: list[PreparedSentence]) -> None:
    current.headings = _shared(current.headings, scope.headings)
    first_heading = current.passages[0].heading
    current.heading = first_heading if first_heading in current.headings else None
    deepest = current.headings[-1] if current.headings else None
    current.subheading = deepest if deepest != current.heading else None
    current.passages.extend(passages)
    current.members.append(list(scope.headings))


def _shared(left: list[str], right: list[str]) -> list[str]:
    shared: list[str] = []
    for one, other in zip(left, right):
        if one != other:
            break
        shared.append(one)
    return shared


def _size(passages: list[PreparedSentence]) -> int:
    return sum(len(passage.text) for passage in passages) + 2 * max(0, len(passages) - 1)
