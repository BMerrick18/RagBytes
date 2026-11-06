"""Run the two embedding passes and return chunks."""

from ragbytes.chunk.semantic.boundaries import first_pass_cuts, second_pass_cuts
from ragbytes.chunk.semantic.chunks import chunk_sections, chunks_from_sections, whole_after_first_pass
from ragbytes.chunk.semantic.embed import Embedder, embed_texts
from ragbytes.chunk.semantic.embed_prep import HeadingPassages, PreparedSentence, prepare_sentences
from ragbytes.schemas import Chunk, Section


def chunk_semantic(sections: list[Section], *, filename: str, embedder: Embedder) -> list[Chunk]:
    """Chunk a document from embedding similarity, one heading path at a time.

    Both embedding passes cover the whole document, because headings do not
    depend on each other. The first pass embeds every long paragraph and long
    list, under every heading, as one list. Each heading is then cut from its
    own slice of those vectors, and the split pieces are joined back into
    sections. The second pass embeds those sections together with the short
    passages, tables, and figures, again as one list. Each heading is cut from
    its own slice. A sharp drop between neighbours starts a new chunk. Where
    the similarity stays close, several passages share one chunk. A chunk
    never crosses into the next heading or subheading.

    The embedder sees passage text, without the heading path. The path is
    written onto each finished chunk for a later search embedding. A heading
    with fewer than two passages to compare is left out of that pass.
    """
    originals = {section.id: section for section in sections}
    passages_by_heading = _after_first_pass(prepare_sentences(sections), embedder)
    cuts_by_heading = _second_cuts(passages_by_heading, embedder)
    built: list[Section] = []
    for passages, cuts in zip(passages_by_heading, cuts_by_heading, strict=True):
        built.extend(chunk_sections(passages, cuts, originals, start_index=len(built)))
    return chunks_from_sections(built, filename=filename)


def _after_first_pass(scopes: list[HeadingPassages], embedder: Embedder) -> list[list[PreparedSentence]]:
    """Return the second-pass passages for every heading, in file order.

    Long blocks from every heading are embedded together. The cuts for one
    heading use only that heading's vectors.
    """
    texts = [
        passage.text
        for scope in scopes
        if len(scope.to_embed) >= 2
        for passage in scope.to_embed
    ]
    vectors = embed_texts(texts, embedder)
    cursor = 0
    ready: list[list[PreparedSentence]] = []
    for scope in scopes:
        if len(scope.to_embed) < 2:
            ready.append(whole_after_first_pass(scope))
            continue
        count = len(scope.to_embed)
        cuts = first_pass_cuts(scope.to_embed, vectors[cursor : cursor + count])
        ready.append(whole_after_first_pass(scope, cuts))
        cursor += count
    _check_consumed(cursor, vectors, "first")
    return ready


def _second_cuts(groups: list[list[PreparedSentence]], embedder: Embedder) -> list[list[int]]:
    """Return where each heading splits, in file order.

    Neighbour lists from every heading are embedded together. A heading with
    fewer than two passages is not embedded and has no cuts.
    """
    texts = [
        passage.text
        for passages in groups
        if len(passages) >= 2
        for passage in passages
    ]
    vectors = embed_texts(texts, embedder)
    cursor = 0
    cuts: list[list[int]] = []
    for passages in groups:
        if len(passages) < 2:
            cuts.append([])
            continue
        count = len(passages)
        cuts.append(second_pass_cuts(vectors[cursor : cursor + count]))
        cursor += count
    _check_consumed(cursor, vectors, "second")
    return cuts


def _check_consumed(cursor: int, vectors: list[list[float]], phase: str) -> None:
    if cursor != len(vectors):
        raise RuntimeError(f"The {phase} pass used {cursor} of {len(vectors)} vectors.")
