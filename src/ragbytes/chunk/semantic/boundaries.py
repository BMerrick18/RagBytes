"""Decide where neighbouring passages stop sharing a subject."""

import statistics

from ragbytes.chunk.semantic.embed_prep import PreparedSentence

# One join has no neighbours to compare with, so it uses a fixed floor.
# Several joins cut where a score falls well below the middle of that group.
_SINGLE_JOIN_FLOOR = 0.5
_OUTLIER_DROP = 0.15


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


def first_pass_cuts(passages: list[PreparedSentence], vectors: list[list[float]]) -> dict[int, list[int]]:
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
        found = cut_indexes(group_vectors)
        if found:
            cuts[group_id] = found
    return cuts


def second_pass_cuts(vectors: list[list[float]]) -> list[int]:
    """Return the indexes, inside one heading, where a new chunk starts."""
    return cut_indexes(vectors)


def cut_indexes(vectors: list[list[float]]) -> list[int]:
    """Return the indexes at which a new run should start.

    The score between two neighbours is their cosine similarity. A lone join
    splits when that score is below 0.5. With more joins, a score also splits
    when it falls more than 0.15 below the middle score of the same run. The
    first passage is never listed: a run always starts at 0.
    """
    if len(vectors) < 2:
        return []
    scores = [cosine(vectors[index - 1], vectors[index]) for index in range(1, len(vectors))]
    if len(scores) == 1:
        return [1] if scores[0] < _SINGLE_JOIN_FLOOR else []
    middle = statistics.median(scores)
    return [
        index + 1
        for index, score in enumerate(scores)
        if score < _SINGLE_JOIN_FLOOR or score < middle - _OUTLIER_DROP
    ]


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
