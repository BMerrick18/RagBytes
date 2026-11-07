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

    Two headings join when either is that small, they share at least one
    heading above them, and both sit no more than one level below that
    shared path: siblings, or a parent's opening text and its first child.
    The shared path is what a chunk that spans them is labelled with, so two
    outermost headings never join: there is no heading that honestly covers
    both, and a chunk with no heading path is harder to find than two small
    chunks with the right one. A heading change between two larger headings
    is still always a boundary. A parent's opening text is the start of its
    own subjects, so it waits for its first child rather than joining the
    heading before it. Joining only lets the second pass compare them, so
    passages that are unrelated are still cut apart there. A style that does
    not merge headings keeps every heading as its own umbrella. A preamble
    with no heading path, shorter than the tiny size, is written as a title
    line on the first real heading after it.
    """
    umbrellas: list[Umbrella] = []
    pending: tuple[HeadingPassages, list[PreparedSentence]] | None = None
    for position, (scope, passages) in enumerate(zip(scopes, ready, strict=True)):
        if not passages:
            continue
        if pending is not None:
            if scope.headings:
                passages = _with_title_line(pending[1], passages)
            else:
                _append_umbrella(umbrellas, pending[0], pending[1])
            pending = None
        following = scopes[position + 1].headings if position + 1 < len(scopes) else None
        if _bare_preamble(scope, passages, style) and _later_heading(scopes, ready, position):
            pending = (scope, passages)
            continue
        current = umbrellas[-1] if umbrellas else None
        if (
            style.merge_headings
            and current is not None
            and not _opens(scope.headings, following)
            and _joins(current, scope.headings, passages, style.min_chars)
        ):
            _absorb(current, scope, passages)
            continue
        _append_umbrella(umbrellas, scope, passages)
    if pending is not None:
        _append_umbrella(umbrellas, pending[0], pending[1])
    return umbrellas


def _append_umbrella(
    umbrellas: list[Umbrella], scope: HeadingPassages, passages: list[PreparedSentence]
) -> None:
    umbrellas.append(
        Umbrella(
            headings=list(scope.headings),
            heading=scope.heading,
            subheading=scope.subheading,
            passages=list(passages),
            members=[list(scope.headings)],
        )
    )


def _bare_preamble(scope: HeadingPassages, passages: list[PreparedSentence], style: Style) -> bool:
    """A short block with an empty heading path, such as a document title."""
    return not scope.headings and _size(passages) < style.tiny_chars


def _later_heading(
    scopes: list[HeadingPassages], ready: list[list[PreparedSentence]], position: int
) -> bool:
    """A later heading has text this preamble can sit above."""
    for scope, passages in zip(scopes[position + 1 :], ready[position + 1 :], strict=True):
        if passages and scope.headings:
            return True
    return False


def _with_title_line(preamble: list[PreparedSentence], passages: list[PreparedSentence]) -> list[PreparedSentence]:
    """Write the preamble once, as a title line, above the first passage."""
    title = "\n".join(passage.text.strip() for passage in preamble if passage.text.strip())
    if not title or not passages:
        return passages
    first = passages[0]
    first.text = f"{title}\n\n{first.text}" if first.text else title
    if first.compare_text is not None:
        first.compare_text = f"{title}\n\n{first.compare_text}" if first.compare_text else title
    return passages


def _opens(headings: list[str], following: list[str] | None) -> bool:
    """The next heading sits directly inside this one."""
    return following is not None and len(following) > len(headings) and following[: len(headings)] == headings


def _joins(current: Umbrella, headings: list[str], passages: list[PreparedSentence], min_chars: int) -> bool:
    if _size(current.passages) >= min_chars and _size(passages) >= min_chars:
        return False
    path = _shared(current.headings, headings)
    if not path:
        return False
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
