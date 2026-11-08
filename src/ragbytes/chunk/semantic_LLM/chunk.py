"""Cut extracted sections by topic and return the shared chunk records."""

from ragbytes.chunk.semantic_LLM.build_chunks import assemble_llm_chunks
from ragbytes.chunk.semantic_LLM.text_prep import ProseRun, segment_sections
from ragbytes.schemas import Chunk, Section


def chunk_llm(sections: list[Section], *, filename: str) -> list[Chunk]:
    """Ask where the topics change, then return chunks with the usual metadata.

    The model sees numbered sentences and returns start indexes and a short
    topic name. An image, chart, table, or complex region is not part of
    that text. A diagram arrives as an image. Each of these is its own
    chunk: the model sees that figure and returns only a short topic title.
    Headings, pages, and the document title stay on our copy. ``topic`` is
    null when the model gives no name. A slice that crosses heading paths
    lists each path once, in file order. The calls store nothing.
    """
    units = segment_sections(sections)
    if not units:
        return []
    from ragbytes.chunk.semantic_LLM.openAI_call import split_document, title_figure

    prose_splits: list[list[tuple[int, str]]] = []
    figure_topics: list[str] = []
    for unit in units:
        if isinstance(unit, ProseRun):
            sentences = [sentence.text for sentence in unit.sentences]
            prose_splits.append(split_document(sentences))
            continue
        figure_topics.append(title_figure(unit.section))
    return assemble_llm_chunks(units, prose_splits, figure_topics, filename=filename)
