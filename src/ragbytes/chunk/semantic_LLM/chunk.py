"""Cut extracted sections by topic and return the shared chunk records."""

from ragbytes.chunk.semantic_LLM.build_chunks import build_chunk_records
from ragbytes.chunk.semantic_LLM.text_prep import tag_sentences
from ragbytes.schemas import Chunk, Section


def chunk_llm(sections: list[Section], *, filename: str) -> list[Chunk]:
    """Ask where the topics change, then return chunks with the usual metadata.

    The model sees numbered sentences and returns start indexes and a short
    topic name. Headings, pages, and the document title stay on our copy of
    each sentence. ``topic`` is null when the model gives no name. A slice
    that crosses heading paths lists each path once, in file order. The call
    stores nothing.
    """
    tagged = tag_sentences(sections)
    if not tagged:
        return []
    from ragbytes.chunk.semantic_LLM.openAI_call import split_document

    splits = split_document([sentence.text for sentence in tagged])
    return build_chunk_records(tagged, splits, filename=filename)
