"""Decide where neighbouring passages stop sharing a subject."""

import statistics

from ragbytes.chunk.semantic.embed_prep import PreparedSentence
from ragbytes.chunk.semantic.styles import BALANCED, Style

# With several joins, a dip also cuts when it falls this far, or one standard
# deviation if that is more, below the middle score of the run. The step is
# wider than the noise between two single sentences.
_MIN_DROP = 0.08
# Each side of a join is the mean of up to this many passages, so one short
# passage does not decide a boundary on its own.
_WINDOW = 2
_SENTENCE_ENDS = (".", "!", "?")
_FRAGMENT_KINDS = frozenset({"text", "list"})


def cosine(left: list[float], right: list[float]) -> float:
    """Return the cosine similarity of two vectors, from -1 to 1.

    OpenAI embedding vectors are already length 1, so this is their dot
    product. Other vectors are scaled here, which keeps a test double honest.
    """
    if len(left) != len(right) or not left:
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for one, other in zip(left, right, strict=True):
        dot += one * other
        left_norm += one * one
        right_norm += other * other
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / ((left_norm**0.5) * (right_norm**0.5))


def neighbour_scores(vectors: list[list[float]]) -> list[float]:
    """Return the score between each passage and the one after it."""
    return [cosine(vectors[index - 1], vectors[index]) for index in range(1, len(vectors))]


def first_pass_cuts(
    passages: list[PreparedSentence], vectors: list[list[float]], style: Style = BALANCED
) -> dict[int, list[int]]:
    """Return where each long block splits, as indexes inside that group.

    Passages that share a ``group`` are one paragraph or one list. A cut index
    is the first sentence of a new section. Groups are not compared with each
    other. A group with no cut stays one section.
    """
    if len(passages) != len(vectors):
        raise RuntimeError(f"Cannot compare {len(passages)} passages with {len(vectors)} vectors.")
    cuts: dict[int, list[int]] = {}
    for group_id, indexes in _groups(passages):
        group_vectors = [vectors[index] for index in indexes]
        found = cut_indexes(
            group_vectors,
            [len(passages[index].text) for index in indexes],
            style,
            plain_bisection=True,
        )
        if found:
            cuts[group_id] = found
    return cuts


def second_pass_cuts(
    vectors: list[list[float]], lengths: list[int] | None = None, style: Style = BALANCED
) -> list[int]:
    """Return the indexes, inside one heading or joined group of headings, where a new chunk starts."""
    return cut_indexes(vectors, lengths, style)


def join_scores(vectors: list[list[float]]) -> list[float]:
    """Return one score per join: the passages just before it against those just after.

    Score ``j`` sits between passage ``j`` and passage ``j + 1``. Where both
    sides have room, each side is the mean of two passages and the sides never
    share one. Next to either end of the run, the two passages are compared
    alone, because a side with fewer passages scores lower on its own.
    """
    scores: list[float] = []
    for join in range(1, len(vectors)):
        width = _WINDOW if _is_wide(join, len(vectors)) else 1
        left = _mean(vectors[join - width : join])
        right = _mean(vectors[join : join + width])
        scores.append(cosine(left, right))
    return scores


def cut_indexes(
    vectors: list[list[float]],
    lengths: list[int] | None = None,
    style: Style = BALANCED,
    *,
    plain_bisection: bool = False,
) -> list[int]:
    """Return the indexes at which a new run should start.

    A lone join splits when its score is below the style's floor. With more
    joins, a score also splits when it sits well below the middle score of
    joins of the same shape, and a windowed join must also be a dip, lower
    than the joins on either side. With ``lengths``, a run longer than the
    style's maximum is split into the fewest pieces, preferring the lowest
    neighbour-score cuts and then the most even sizes. Size and short-run
    decisions use the single-passage neighbour scores, so an end join is not
    compared with a windowed one. The first pass, with ``plain_bisection``,
    bisects a run that has no join below both the relative bar and the floor.
    A run under the style's minimum joins the neighbour it is closer to,
    unless that neighbour is below the floor or the joined run would be too
    long. The first passage is never listed: a run always starts at 0.
    """
    if len(vectors) < 2:
        return []
    scores = join_scores(vectors)
    pairs = neighbour_scores(vectors)
    cuts = _topic_cuts(vectors, scores, style.floor)
    if lengths is None:
        return cuts
    if len(lengths) != len(vectors):
        raise RuntimeError(f"Cannot size {len(vectors)} passages from {len(lengths)} lengths.")
    if plain_bisection and not _below_both(pairs, style.floor):
        cuts = []
    starts = _split_long(
        sorted({0, *cuts}), pairs, lengths, style, even=plain_bisection and not cuts
    )
    return [start for start in _merge_short(starts, pairs, lengths, style) if start]


def attach_fragments(passages: list[PreparedSentence], cuts: list[int], style: Style = BALANCED) -> list[int]:
    """Join each run that is too small to stand alone to a neighbour, whatever its score.

    A fragment is text under the style's fragment size that does not end like
    a sentence, such as ``September 2026`` or ``ISBN: 978-1-4731-3145-3``. It
    says little on its own, so it joins the run after it, which it usually
    introduces, or the run before it at the end. A run that ends with ``:`` or
    ``;`` and is no longer than the minimum joins the run it introduces. A
    short run that already mixes a described image with text may join a
    neighbouring text run. A tiny run is text under the style's tiny size,
    such as a one-line closing remark. Its score against its neighbours is
    often low, because a short sentence shares few words with the paragraphs
    around it, yet on its own it is too little to find or to read. It joins
    the text run before it, which it usually concludes, or the run after it
    at the start, when the joined run still fits the style's maximum. A
    fragment is not joined onto a table, a code block, or a figure, and a
    figure that stands alone keeps its bytes.
    """
    starts = sorted({0, *(cut for cut in cuts if 0 < cut < len(passages))})
    while len(starts) > 1:
        bounds = [*starts, len(passages)]
        runs = list(zip(bounds, bounds[1:]))
        removed = next(
            (
                removed
                for position, run in enumerate(runs)
                if (removed := _join_target(passages, runs, position, style)) is not None
            ),
            None,
        )
        if removed is None:
            break
        starts.remove(removed)
    return [start for start in starts if start]


def _join_target(
    passages: list[PreparedSentence], runs: list[tuple[int, int]], position: int, style: Style
) -> int | None:
    """Return the start index to remove so this run joins a neighbour, or None to leave it."""
    begin, end = runs[position]
    part = passages[begin:end]
    text = "\n\n".join(passage.text for passage in part).strip()
    if _described_image_text(part, text, style):
        return _text_neighbour(passages, runs, part, position, style, forward_first=True)
    if any(passage.kind not in _FRAGMENT_KINDS for passage in part):
        return None
    if _introducer(text, style):
        forward = _text_neighbour(passages, runs, part, position, style, forward_first=True, forward_only=True)
        if forward is not None:
            return forward
    if len(text) < style.fragment_chars and not text.endswith(_SENTENCE_ENDS):
        return _text_neighbour(passages, runs, part, position, style, forward_first=True)
    if len(text) >= style.tiny_chars:
        return None
    return _text_neighbour(passages, runs, part, position, style, forward_first=False)


def _introducer(text: str, style: Style) -> bool:
    """A colon or semicolon ending, no longer than the minimum, introduces the next run."""
    stripped = text.rstrip()
    return bool(stripped) and len(stripped) <= style.min_chars and stripped.endswith((":", ";"))


def _described_image_text(part: list[PreparedSentence], text: str, style: Style) -> bool:
    """A short run that already mixes a described image with text."""
    if len(text) > style.min_chars:
        return False
    kinds = {passage.kind for passage in part}
    if "image" not in kinds or not kinds.intersection(_FRAGMENT_KINDS):
        return False
    if not kinds.issubset(_FRAGMENT_KINDS | {"image"}):
        return False
    return any(passage.kind == "image" and "[Image:" in passage.text for passage in part)


def _text_neighbour(
    passages: list[PreparedSentence],
    runs: list[tuple[int, int]],
    part: list[PreparedSentence],
    position: int,
    style: Style,
    *,
    forward_first: bool,
    forward_only: bool = False,
) -> int | None:
    """Join this run to a text neighbour that keeps the result inside the maximum."""
    begin, end = runs[position]
    options: list[tuple[int, int]] = []
    if position + 1 < len(runs):
        options.append((end, position + 1))
    if not forward_only and position > 0:
        options.append((begin, position - 1))
    if not forward_first:
        options.reverse()
    for start, neighbour in options:
        other = passages[slice(*runs[neighbour])]
        if any(passage.kind not in _FRAGMENT_KINDS for passage in other):
            continue
        joined = sum(len(passage.text) for passage in [*part, *other]) + 2 * (len(part) + len(other) - 1)
        if joined <= style.max_chars:
            return start
    return None


def _topic_cuts(vectors: list[list[float]], scores: list[float], floor: float) -> list[int]:
    """Cut below the floor, or where a score sits well below others of the same shape.

    Windowed scores run higher than scores between two lone passages, so each
    kind is measured against its own kind: a wide join against the other wide
    joins, and an end join against every neighbour pair in the run.
    """
    if len(scores) == 1:
        return [1] if scores[0] < floor else []
    pairs = neighbour_scores(vectors)
    wide = [_is_wide(join + 1, len(vectors)) for join in range(len(scores))]
    wide_scores = [score for score, is_wide in zip(scores, wide, strict=True) if is_wide]
    wide_bar = _bar(wide_scores) if len(wide_scores) >= 2 else None
    pair_bar = _bar(pairs)
    cuts: list[int] = []
    for join, score in enumerate(scores):
        if score < floor:
            cuts.append(join + 1)
        elif wide[join] and wide_bar is not None:
            if score < wide_bar and _is_dip(scores, wide, join):
                cuts.append(join + 1)
        elif pairs[join] < pair_bar:
            cuts.append(join + 1)
    return cuts


def _bar(scores: list[float]) -> float:
    return statistics.median(scores) - max(_MIN_DROP, statistics.pstdev(scores))


def _below_both(pairs: list[float], floor: float) -> bool:
    """A join under the relative bar and under the floor is a real subject change."""
    if not pairs:
        return False
    if len(pairs) == 1:
        return pairs[0] < floor
    limit = min(_bar(pairs), floor)
    return any(score < limit for score in pairs)


def _is_wide(join: int, count: int) -> bool:
    """Both sides of the join before passage ``join`` have room for a full window."""
    return join >= _WINDOW and count - join >= _WINDOW


def _is_dip(scores: list[float], wide: list[bool], join: int) -> bool:
    """A score below the wide join before it and no higher than the wide join after it."""
    if join > 0 and wide[join - 1] and scores[join] >= scores[join - 1]:
        return False
    return not (join + 1 < len(scores) and wide[join + 1] and scores[join] > scores[join + 1])


def _split_long(
    starts: list[int], scores: list[float], lengths: list[int], style: Style, *, even: bool = False
) -> list[int]:
    """Cut each run over the limit into the fewest pieces that fit.

    ``scores`` are single-passage neighbour scores. The lowest total cut score
    wins after the piece count. ``even`` bisects instead, then uses the score
    only to break a tie. A single passage that is still too long is left for
    the caller to split inside the text.
    """
    bounds = [*starts, len(lengths)]
    chosen = list(starts)
    for begin, end in zip(bounds, bounds[1:]):
        chosen.extend(_partition(begin, end, scores, lengths, style, even=even))
    return sorted(set(chosen))


def _partition(
    begin: int, end: int, scores: list[float], lengths: list[int], style: Style, *, even: bool
) -> list[int]:
    """Return cut indexes inside ``(begin, end)`` for one run."""
    count = end - begin
    if count < 2 or _size(lengths, begin, end) <= style.max_chars:
        return []
    limit = style.max_chars
    # pieces, cut-score sum, sum of squared sizes, previous offset
    bests: list[tuple[float, float, float, int] | None] = [None] * (count + 1)
    bests[0] = (0.0, 0.0, 0.0, 0)
    for index in range(1, count + 1):
        best: tuple[float, float, float, int] | None = None
        best_key: tuple[float, float, float] | None = None
        for start in range(index - 1, -1, -1):
            previous = bests[start]
            if previous is None:
                continue
            size = _size(lengths, begin + start, begin + index)
            if size > limit and index - start > 1:
                break
            cut_score = 0.0 if start == 0 else scores[begin + start - 1]
            pieces = previous[0] + 1
            score_sum = previous[1] + cut_score
            square = previous[2] + float(size * size)
            key = (pieces, square, score_sum) if even else (pieces, score_sum, square)
            if best is None or best_key is None or key < best_key:
                best = (pieces, score_sum, square, start)
                best_key = key
        bests[index] = best
    cuts: list[int] = []
    cursor = count
    while cursor > 0:
        plan = bests[cursor]
        if plan is None:
            break
        start = plan[3]
        if start > 0:
            cuts.append(begin + start)
        cursor = start
    return cuts


def _merge_short(starts: list[int], scores: list[float], lengths: list[int], style: Style) -> list[int]:
    """Join a short run to its closer neighbour, best match first, while the result fits."""
    starts = list(starts)
    while True:
        bounds = [*starts, len(lengths)]
        best: tuple[float, int] | None = None
        for position, (begin, end) in enumerate(zip(bounds, bounds[1:])):
            if _size(lengths, begin, end) >= style.min_chars:
                continue
            options: list[tuple[float, int, int]] = []
            if position > 0:
                options.append((scores[begin - 1], begin, _size(lengths, bounds[position - 1], end)))
            if end < len(lengths):
                options.append((scores[end - 1], end, _size(lengths, begin, bounds[position + 2])))
            for score, start, merged in options:
                if score >= style.floor and merged <= style.max_chars and (best is None or score > best[0]):
                    best = (score, start)
        if best is None:
            return starts
        starts.remove(best[1])


def _size(lengths: list[int], begin: int, end: int) -> int:
    """Characters in passages ``begin`` to ``end``, joined by a blank line."""
    return sum(lengths[begin:end]) + 2 * max(0, end - begin - 1)


def _mean(vectors: list[list[float]]) -> list[float]:
    """Average unit-length copies, so a longer vector does not outweigh the rest."""
    total = [0.0] * len(vectors[0])
    for vector in vectors:
        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        for index, value in enumerate(vector):
            total[index] += value / norm
    return total


def _groups(passages: list[PreparedSentence]) -> list[tuple[int, list[int]]]:
    groups: list[tuple[int, list[int]]] = []
    for index, passage in enumerate(passages):
        if passage.group is None:
            continue
        if groups and groups[-1][0] == passage.group:
            groups[-1][1].append(index)
            continue
        groups.append((passage.group, [index]))
    return groups
