from ragbytes.chunk.semantic.boundaries import cosine, cut_indexes, first_pass_cuts
from ragbytes.chunk.semantic.embed_prep import PreparedSentence


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


def test_each_embed_group_is_judged_on_its_own():
    passages = [_passage(0, 0), _passage(0, 1), _passage(1, 2), _passage(1, 3)]
    same = [1.0, 0.0]
    other = [0.0, 1.0]

    cuts = first_pass_cuts(passages, [same, other, same, same])

    assert cuts == {0: [1]}
