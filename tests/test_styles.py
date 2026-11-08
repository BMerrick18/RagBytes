import statistics

import pytest

from ragbytes.chunk.semantic_embed.boundaries import attach_fragments, cut_indexes
from ragbytes.chunk.semantic_embed.embed_prep import PreparedSentence
from ragbytes.chunk.semantic_embed.styles import BALANCED, STYLES, for_document, resolve_style


def _passage(text: str, order: int, kind: str = "text") -> PreparedSentence:
    return PreparedSentence(
        text=text,
        embed_text=text,
        headings=["Guide"],
        heading="Guide",
        subheading=None,
        page=None,
        section_index=order,
        section_id=f"section-{order}",
        file_id="file",
        kind=kind,
        order=order,
        group=None,
    )


def test_styles_run_from_small_focused_chunks_to_large_ones():
    precise, balanced, broad = STYLES["precise"], STYLES["balanced"], STYLES["broad"]

    assert precise.max_chars < balanced.max_chars < broad.max_chars
    assert precise.min_chars < balanced.min_chars < broad.min_chars
    assert precise.floor > balanced.floor > broad.floor


def test_a_style_cuts_long_runs_at_its_own_maximum():
    vectors = [[1.0, 0.0]] * 6
    lengths = [490] * 6

    assert cut_indexes(vectors, lengths, STYLES["precise"]) == [2, 4]
    assert cut_indexes(vectors, lengths, STYLES["balanced"]) == [3]
    assert cut_indexes(vectors, lengths, STYLES["broad"]) == []


def test_overrides_cap_the_size_and_keep_headings_apart():
    style = resolve_style("broad", strict_headings=True, max_chars=800)

    assert style.name == "broad"
    assert style.max_chars == 800
    assert style.min_chars == 200
    assert style.merge_headings is False


def test_a_short_document_keeps_the_style_floor():
    assert for_document(BALANCED, [0.1] * 19).floor == BALANCED.floor


def test_a_document_that_scores_low_throughout_lowers_its_floor_within_the_style_range():
    low = for_document(BALANCED, [0.25, 0.35] * 15)
    very_low = for_document(BALANCED, [0.05, 0.1] * 15)
    high = for_document(BALANCED, [0.6, 0.7] * 15)

    assert low.floor == pytest.approx(0.275)
    assert very_low.floor == BALANCED.floor_low
    assert high.floor == pytest.approx(BALANCED.floor + 0.04)
    assert high.floor <= statistics.median([0.6, 0.7] * 15)


def test_a_high_scoring_document_keeps_the_three_styles_apart():
    scores = [0.6, 0.7] * 15
    precise, balanced, broad = (for_document(STYLES[name], scores) for name in ("precise", "balanced", "broad"))

    assert precise.floor > balanced.floor > broad.floor
    assert precise.floor <= STYLES["precise"].floor + 0.04
    assert broad.floor >= STYLES["broad"].floor


def test_a_spread_out_document_keeps_the_style_floor():
    scores = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8] * 4

    assert for_document(BALANCED, scores).floor == BALANCED.floor
    assert for_document(STYLES["precise"], scores).floor == STYLES["precise"].floor


def test_a_date_joins_the_run_after_it():
    passages = [_passage("September 2026", 0), _passage("This guide covers urgent care.", 1)]

    assert attach_fragments(passages, [1]) == []


def test_a_label_at_the_end_joins_the_run_before_it():
    passages = [_passage("This guide covers urgent care.", 0), _passage("ISBN: 978-1-4731-3145-3", 1)]

    assert attach_fragments(passages, [1]) == []


_LAMP = (
    "Warm the lamp before the crew arrives, then check the wick and the glass "
    "so the light carries across the water to the far pier."
)
_TARIFF = (
    "The tariff changed the quay fees for every vessel this season, and the "
    "harbour office posted the new rates on the gate by the lock."
)


def test_a_sentence_above_the_tiny_size_is_not_a_fragment():
    passages = [_passage(_LAMP, 0), _passage(_TARIFF, 1)]

    assert attach_fragments(passages, [1]) == [1]


def test_a_tiny_sentence_joins_the_text_before_it_whatever_its_score():
    passages = [_passage(_LAMP, 0), _passage("Access control is covered in a separate memo.", 1)]

    assert attach_fragments(passages, [1]) == []


def test_a_tiny_sentence_at_the_start_joins_the_text_after_it():
    passages = [_passage("Warm the lamp.", 0), _passage(_TARIFF, 1)]

    assert attach_fragments(passages, [1]) == []


def test_a_tiny_sentence_prefers_the_run_before_it():
    passages = [_passage(_LAMP, 0), _passage("Warm the lamp.", 1), _passage(_TARIFF, 2)]

    assert attach_fragments(passages, [1, 2]) == [2]


def test_a_tiny_sentence_does_not_join_a_table_or_a_figure():
    passages = [
        _passage("| A | B |", 0, kind="table"),
        _passage("Warm the lamp.", 1),
        _passage("[Image: Wiring]", 2, kind="image"),
    ]

    assert attach_fragments(passages, [1, 2]) == [1, 2]


def test_a_tiny_sentence_stays_alone_when_the_join_would_pass_the_maximum():
    passages = [_passage("x" * 1990 + ".", 0), _passage("Warm the lamp.", 1)]

    assert attach_fragments(passages, [1]) == [1]


def test_a_short_table_is_not_a_fragment():
    passages = [_passage("| A | B |", 0, kind="table"), _passage(_TARIFF, 1)]

    assert attach_fragments(passages, [1]) == [1]
