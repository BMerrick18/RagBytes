"""Cut extracted sections by topic and return the shared chunk records."""

from ragbytes.chunk.semantic_LLM.build_chunks import assemble_llm_chunks, bound_splits
from ragbytes.chunk.semantic_LLM.text_prep import ProseRun, absorb_captions, segment_sections
from ragbytes.schemas import Chunk, Section


def chunk_llm(sections: list[Section], *, filename: str) -> list[Chunk]:
    """Ask where the topics change, then return chunks with the usual metadata.

    The model sees numbered sentences, with the heading written above the
    lines it covers. A list and a block of code are each one entry, so a cut
    cannot start on each line, and the chunk keeps those lines. A heading
    change starts a chunk, unless both headings are short and share a parent.
    A short fragment joins the neighbour under the same heading. A short
    caption is written onto the figure it introduces.
    An image, chart, table, or complex region is not part of that text. A
    diagram arrives as an image. Each of these is its own chunk: the model
    sees that figure and returns only a short topic title.
    Headings, pages, and the document title stay on our copy. ``topic`` is
    null when the model gives no name. A slice that crosses heading paths
    lists each path once, in file order. The calls store nothing.
    """
    units = absorb_captions(segment_sections(sections))
    if not units:
        return []
    from ragbytes.chunk.semantic_LLM.openAI_call import split_document, title_figure

    prose_splits: list[list[tuple[int, str]]] = []
    figure_topics: list[str] = []
    for unit in units:
        if isinstance(unit, ProseRun):
            sentences = [sentence.text for sentence in unit.sentences]
            splits = split_document(
                sentences, headings=[list(sentence.headings) for sentence in unit.sentences]
            )
            prose_splits.append(bound_splits(unit.sentences, splits))
            continue
        figure_topics.append(title_figure(unit.section))
    return assemble_llm_chunks(units, prose_splits, figure_topics, filename=filename)
