"""Run the two embedding passes and return chunks."""

from ragbytes.chunk.semantic.boundaries import attach_fragments, first_pass_cuts, neighbour_scores, second_pass_cuts
from ragbytes.chunk.semantic.chunks import chunk_sections, chunks_from_sections, whole_after_first_pass
from ragbytes.chunk.semantic.embed import Embedder, embed_texts
from ragbytes.chunk.semantic.embed_prep import HeadingPassages, PreparedSentence, prepare_sentences
from ragbytes.chunk.semantic.siblings import merge_small_headings
from ragbytes.chunk.semantic.styles import BALANCED, Style, for_document
from ragbytes.schemas import Chunk, Section


def chunk_semantic(
    sections: list[Section], *, filename: str, embedder: Embedder, style: Style = BALANCED
) -> list[Chunk]:
    """Chunk a document from embedding similarity, one heading path at a time.

    Both embedding passes cover the whole document, because headings do not
    depend on each other. The first pass embeds every long paragraph and long
    list, under every heading, as one list. Each heading is then cut from its
    own slice of those vectors, and the split pieces are joined back into
    sections. A heading under the style's minimum size then joins the sibling
    heading beside it. The second pass embeds those sections together with
    the short passages, tables, and figures, again as one list. Each heading,
    or group of joined headings, is cut from its own slice. A sharp drop
    between the passages either side of a join starts a new chunk. Where the
    similarity stays close, several passages share one chunk. A chunk grows
    to the style's maximum before it is split at its weakest join, and a
    chunk under the minimum joins its closer neighbour unless both are
    unrelated. A short label or date always joins a neighbour. A heading
    change between two larger headings always starts a new chunk.

    Each pass sets its own floor for unrelated neighbours from that pass's
    scores, so a document whose passages score low as a rule is not cut at
    every join. The embedder sees passage text, without the heading path. The
    path is written onto each finished chunk for a later search embedding. A
    chunk that spans joined headings takes the path they share, with each
    heading's own title written above its text. A heading with fewer than two
    passages to compare is left out of that pass.
    """
    originals = {section.id: section for section in sections}
    scopes = prepare_sentences(sections)
    umbrellas = merge_small_headings(scopes, _after_first_pass(scopes, embedder, style), style)
    cuts_by_umbrella = _second_cuts([umbrella.passages for umbrella in umbrellas], embedder, style)
    built: list[Section] = []
    for umbrella, cuts in zip(umbrellas, cuts_by_umbrella, strict=True):
        kept = attach_fragments(umbrella.passages, cuts, style)
        built.extend(
            chunk_sections(umbrella.passages, kept, originals, start_index=len(built), umbrella=umbrella)
        )
    return chunks_from_sections(built, filename=filename)


def _after_first_pass(
    scopes: list[HeadingPassages], embedder: Embedder, style: Style
) -> list[list[PreparedSentence]]:
    """Return the second-pass passages for every heading, in file order.

    Long blocks from every heading are embedded together. The cuts for one
    heading use only that heading's vectors.
    """
    texts = [
        passage.vector_text
        for scope in scopes
        if len(scope.to_embed) >= 2
        for passage in scope.to_embed
    ]
    vectors = embed_texts(texts, embedder)
    slices: list[list[list[float]] | None] = []
    cursor = 0
    for scope in scopes:
        if len(scope.to_embed) < 2:
            slices.append(None)
            continue
        slices.append(vectors[cursor : cursor + len(scope.to_embed)])
        cursor += len(scope.to_embed)
    _check_consumed(cursor, vectors, "first")
    tuned = for_document(style, _first_pass_scores(scopes, slices))
    ready: list[list[PreparedSentence]] = []
    for scope, scope_vectors in zip(scopes, slices, strict=True):
        if scope_vectors is None:
            ready.append(whole_after_first_pass(scope))
            continue
        ready.append(whole_after_first_pass(scope, first_pass_cuts(scope.to_embed, scope_vectors, tuned)))
    return ready


def _first_pass_scores(scopes: list[HeadingPassages], slices: list[list[list[float]] | None]) -> list[float]:
    """Neighbour scores between pieces of the same long block, across the document."""
    scores: list[float] = []
    for scope, scope_vectors in zip(scopes, slices, strict=True):
        if scope_vectors is None:
            continue
        pairs = neighbour_scores(scope_vectors)
        for index, score in enumerate(pairs):
            if scope.to_embed[index].group == scope.to_embed[index + 1].group:
                scores.append(score)
    return scores


def _second_cuts(groups: list[list[PreparedSentence]], embedder: Embedder, style: Style) -> list[list[int]]:
    """Return where each heading splits, in file order.

    Neighbour lists from every heading are embedded together. A heading with
    fewer than two passages is not embedded and has no cuts.
    """
    texts = [
        passage.vector_text
        for passages in groups
        if len(passages) >= 2
        for passage in passages
    ]
    vectors = embed_texts(texts, embedder)
    slices: list[list[list[float]] | None] = []
    cursor = 0
    for passages in groups:
        if len(passages) < 2:
            slices.append(None)
            continue
        slices.append(vectors[cursor : cursor + len(passages)])
        cursor += len(passages)
    _check_consumed(cursor, vectors, "second")
    tuned = for_document(
        style, [score for group_vectors in slices if group_vectors for score in neighbour_scores(group_vectors)]
    )
    cuts: list[list[int]] = []
    for passages, group_vectors in zip(groups, slices, strict=True):
        if group_vectors is None:
            cuts.append([])
            continue
        lengths = [len(passage.text) for passage in passages]
        cuts.append(second_pass_cuts(group_vectors, lengths, tuned))
    return cuts


def _check_consumed(cursor: int, vectors: list[list[float]], phase: str) -> None:
    if cursor != len(vectors):
        raise RuntimeError(f"The {phase} pass used {cursor} of {len(vectors)} vectors.")
