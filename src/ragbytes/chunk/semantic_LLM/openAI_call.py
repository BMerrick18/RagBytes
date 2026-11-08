"""Ask a model where the numbered sentences change topic."""

from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is missing. Add it to .env in the project root.")
client = OpenAI(api_key=api_key)


import json
from dataclasses import dataclass

# A dated name stays one model. An undated name can later point at a newer one.
DEFAULT_MODEL = "gpt-4o-mini-2024-07-18"
# One call reads about this many sentences. The range to stay inside is 100–200.
WINDOW_SENTENCES = 150

_INSTRUCTIONS = """\
You split a document into chunks by topic.

The user message is the document, one sentence per line.
Each line starts with its index in square brackets, like [0].

Return one entry per chunk.
start is the index of the sentence where that chunk begins.
title is a short name for that topic.

The first entry always has start 0.
Add another entry only where the subject changes.
Use the indexes from the user message. Do not write the sentences back.
"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "chunks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "integer"},
                    "title": {"type": "string"},
                },
                "required": ["start", "title"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["chunks"],
    "additionalProperties": False,
}


@dataclass
class SplitPoint:
    """One cut the model asked for. The numbers are not checked yet."""

    start: int
    title: str


def ask_for_splits(numbered: str, *, model: str = DEFAULT_MODEL) -> list[SplitPoint]:
    """Ask for the sentence indexes where a new topic starts.

    ``numbered`` is the view from ``number_sentences``. An empty view makes
    no request. The call uses the module ``client``, which was built from
    ``OPENAI_API_KEY`` in ``.env``.
    """
    if not numbered.strip():
        return []
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": _INSTRUCTIONS},
            {"role": "user", "content": numbered},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "split_points",
                "strict": True,
                "schema": _SCHEMA,
            },
        },
    )
    return _read_splits(response)


def _read_splits(response) -> list[SplitPoint]:
    message = response.choices[0].message
    if message.refusal:
        raise RuntimeError("The model refused to split the document.")
    if not message.content:
        raise RuntimeError("The model returned no split points.")
    parsed = json.loads(message.content)
    return [
        SplitPoint(start=chunk["start"], title=chunk["title"])
        for chunk in parsed["chunks"]
    ]


def checked_splits(points: list[SplitPoint], sentence_count: int) -> list[SplitPoint]:
    """Drop cuts that do not point at a real sentence.

    A start is kept when it is a whole number from 0 up to, but not
    including, ``sentence_count``. Each start is kept once. The result is
    sorted, and 0 is always present when the document has a sentence.
    """
    if sentence_count <= 0:
        return []
    kept: dict[int, str] = {}
    for point in points:
        start = point.start
        if type(start) is not int:
            continue
        if not 0 <= start < sentence_count:
            continue
        if start in kept:
            continue
        kept[start] = point.title if isinstance(point.title, str) else ""
    kept.setdefault(0, "")
    return [SplitPoint(start=start, title=kept[start]) for start in sorted(kept)]


def _number_window(window: list[str]) -> str:
    """Number one batch from 0. These sentences are already split."""
    return "\n".join(f"[{index}] {sentence}" for index, sentence in enumerate(window))


def next_window(
    points: list[SplitPoint], window_size: int, *, at_end: bool
) -> tuple[list[SplitPoint], int]:
    """Choose the cuts to save, and where the next batch starts.

    The returned index is a position inside this batch. ``window_size`` means
    the next batch begins after this one. At the real end of the document,
    every cut is saved.
    """
    if window_size <= 0:
        return [], 0
    if at_end:
        return points, window_size
    if len(points) <= 1 or points[-1].start <= 0:
        return points[:1], window_size
    return points[:-1], points[-1].start


def split_document(
    sentences: list[str], *, window_size: int = WINDOW_SENTENCES
) -> list[tuple[int, str]]:
    """Return checked ``(start, title)`` pairs for the whole document.

    A document shorter than one batch is a single call, and every cut is
    saved. Longer documents continue from the unsaved last cut.
    """
    if not sentences:
        return []
    collected: list[tuple[int, str]] = []
    seen: set[int] = set()
    cursor = 0
    while cursor < len(sentences):
        window = sentences[cursor : cursor + window_size]
        points = checked_splits(ask_for_splits(_number_window(window)), len(window))
        at_end = cursor + len(window) >= len(sentences)
        keep, resume = next_window(points, len(window), at_end=at_end)
        for point in keep:
            start = cursor + point.start
            if start in seen:
                continue
            seen.add(start)
            collected.append((start, point.title))
        cursor += resume or len(window)
    return collected


if __name__ == "__main__":
    from ragbytes.chunk.semantic_LLM.build_chunks import build_chunks
    from ragbytes.chunk.semantic_LLM.text_prep import number_sentences

    sample = (
        "The company was founded in 2012. "
        "It sells accounting software to small firms. "
        "Revenue grew 40% last year.\n\n"
        "The office dog is named Biscuit. "
        "Biscuit comes to work on Fridays."
    )
    prepared = number_sentences(sample)
    print(prepared.numbered)
    print("---")
    examples = [
        ([SplitPoint(0, "opening"), SplitPoint(3, "later")], 4, False),
        ([SplitPoint(0, "opening")], 4, False),
        ([SplitPoint(0, "opening"), SplitPoint(2, "end")], 2, True),
    ]
    for points, size, at_end in examples:
        keep, resume = next_window(points, size, at_end=at_end)
        print([point.start for point in keep], resume)
    print("---")
    splits = split_document(prepared.sentences)
    for chunk in build_chunks(prepared.sentences, splits):
        print(chunk.start, chunk.title)
        print(chunk.text)
        print("---")
