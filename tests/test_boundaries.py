import math

from ragbytes.chunk.semantic.boundaries import attach_fragments, cosine, cut_indexes, first_pass_cuts
from ragbytes.chunk.semantic.embed_prep import PreparedSentence
from ragbytes.chunk.semantic.styles import BALANCED


def _alike(count: int, score: float) -> list[list[float]]:
    """Unit vectors where every pair scores ``score``: one shared part and one part each."""
    return [
        [math.sqrt(score)] + [math.sqrt(1 - score) if slot == index else 0.0 for slot in range(count)]
        for index in range(count)
    ]


def _at(score: float) -> list[float]:
    """A unit vector that scores ``score`` against ``[1, 0]``."""
    return [score, math.sqrt(1 - score * score)]


def _passage(group: int, order: int) -> PreparedSentence:
    return PreparedSentence(
        text=f"Sentence {order}.",
        embed_text=f"Sentence {order}.",
        headings=["Guide"],
        heading="Guide",
        subheading=None,
        page=None,
        section_index=0,
        section_id="section",
        file_id="file",
        kind="text",
        order=order,
        group=group,
    )


def test_parallel_vectors_score_one_and_opposite_vectors_score_zero():
    assert cosine([1.0, 0.0], [2.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_a_single_low_join_is_a_cut_and_a_close_join_is_not():
    assert cut_indexes([[1.0, 0.0], [0.0, 1.0]]) == [1]
    assert cut_indexes([[1.0, 0.0], [1.0, 0.0]]) == []


def test_a_low_outlier_among_close_joins_is_the_only_cut():
    same = [1.0, 0.0]
    other = [0.0, 1.0]

    cuts = cut_indexes([same, same, same, other, other])

    assert cuts == [3]


def test_related_passages_that_score_below_one_half_stay_together():
    assert cut_indexes(_alike(6, 0.45)) == []
    assert cut_indexes(_alike(2, 0.35)) == []
    assert cut_indexes(_alike(2, 0.25)) == [1]


def test_a_windowed_dip_cuts_once_at_its_lowest_join():
    same = [1.0, 0.0]
    near = _at(0.5)

    assert cut_indexes([same, same, same, near, near, near]) == [3]


def test_a_long_run_splits_evenly_at_its_weakest_join():
    vectors = [[1.0, 0.0]] * 6

    assert cut_indexes(vectors) == []
    assert cut_indexes(vectors, [500] * 6) == [3]


def test_a_short_run_joins_its_closer_neighbour():
    vectors = [_at(0.4), [1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]

    assert cut_indexes(vectors) == [1]
    assert cut_indexes(vectors, [50, 400, 400, 400]) == []


def test_a_short_run_stays_apart_from_unrelated_neighbours():
    vectors = [[1.0, 0.0], [0.0, 1.0], [0.0, 1.0]]

    assert cut_indexes(vectors, [50, 400, 400]) == [1]


def test_a_short_run_is_not_joined_past_the_size_limit():
    vectors = [_at(0.4), [1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]

    assert cut_indexes(vectors, [50, 650, 650, 650]) == [1]


def _with_pair_scores(scores: list[float]) -> list[list[float]]:
    """Unit vectors whose successive neighbour scores are ``scores``."""
    dimension = len(scores) + 1
    vectors = [[0.0] * dimension for _ in range(dimension)]
    vectors[0][0] = 1.0
    for index, score in enumerate(scores):
        fresh = math.sqrt(max(0.0, 1.0 - score * score))
        vectors[index + 1] = [score * value for value in vectors[index]]
        vectors[index + 1][index + 1] = fresh
    return vectors


def test_the_first_pass_bisects_a_long_block_when_no_join_is_low():
    passages = []
    for order in range(4):
        passage = _passage(0, order)
        passage.text = "x" * 600
        passages.append(passage)

    cuts = first_pass_cuts(passages, _with_pair_scores([0.90, 0.95, 0.95]))

    assert cuts == {0: [2]}


def _run(text: str, order: int, kind: str = "text") -> PreparedSentence:
    passage = _passage(None, order)
    passage.text = text
    passage.kind = kind
    passage.group = None
    return passage


def test_a_colon_introducer_joins_the_following_run():
    intro = (
        "26 If the sub-committee decides that the case is proven after hearing the member, "
        "it may impose any of the following:"
    )
    assert BALANCED.tiny_chars < len(intro) <= BALANCED.min_chars
    body = "The panel may warn the member or remove them from the committee."
    passages = [_run(intro, 0), _run(body, 1)]

    assert attach_fragments(passages, [1]) == []


def test_a_short_described_image_run_joins_neighbouring_text():
    body = (
        "Annual leave is booked with the clerk at least a week before the first day away, "
        "and the chair records the dates in the register."
    )
    passages = [
        _run(body, 0),
        _run("[Image: Adopted]", 1, kind="image"),
        _run("ANNUAL LEAVE", 2),
        _run("The clerk keeps the leave book in the office.", 3),
    ]

    assert attach_fragments(passages, [1, 3]) == []


def test_each_embed_group_is_judged_on_its_own():
    passages = [_passage(0, 0), _passage(0, 1), _passage(1, 2), _passage(1, 3)]
    same = [1.0, 0.0]
    other = [0.0, 1.0]

    cuts = first_pass_cuts(passages, [same, other, same, same])

    assert cuts == {0: [1]}
