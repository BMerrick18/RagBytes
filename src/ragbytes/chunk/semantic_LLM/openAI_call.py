"""Ask a model where the numbered sentences change topic, and name a figure."""

import base64
import json
from dataclasses import dataclass

from ragbytes.chunk.semantic_LLM.text_prep import figure_message, numbered_lines
from ragbytes.schemas import Section

# A dated name stays one model. An undated name can later point at a newer one.
DEFAULT_MODEL = "gpt-4o-mini-2024-07-18"
# One call reads about this many sentences. The range to stay inside is 100–200.
WINDOW_SENTENCES = 150

_INSTRUCTIONS = """\
You split a document into chunks by topic.

The user message is the document.
A line that starts with an index in square brackets, like [0], is one entry.
Lines with no index belong to the indexed entry above them.
A line that starts with # is the heading for the entries under it.
A list is one entry. Its items are the lines with no index.
A block of code is one entry too.

Return one entry per chunk.
start is the index where that chunk begins.
title is a short name for that topic.

The first entry always has start 0.
Add another entry only where the subject changes.
Start a new chunk when the heading changes.
A heading that is only a short line may stay with a neighbouring heading on the same subject.
Keep a short line with the other lines under the same heading.
Keep a list with the sentences on the same subject.
Do not give each list item its own chunk.
Do not split a block of code.
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
    no request. The call reads ``OPENAI_API_KEY`` from the environment,
    loading ``.env`` on first use.
    """
    if not numbered.strip():
        return []
    response = _require_client().chat.completions.create(
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


_FIGURE_INSTRUCTIONS = """\
You name one figure from a document.

The user message is that figure.
It may include a picture, a chart, a table, or a diagram.
title is a short topic name of a few words.

Do not describe the figure and do not transcribe it.
"""

_FIGURE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
    },
    "required": ["title"],
    "additionalProperties": False,
}

_client = None


def _require_client():
    """Return the local client, building it from ``OPENAI_API_KEY`` on first use."""
    global _client
    if _client is not None:
        return _client
    import os

    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add it to .env in the project root."
        )
    _client = OpenAI(api_key=api_key)
    return _client


def title_figure(section: Section, *, model: str = DEFAULT_MODEL) -> str:
    """Ask for a short topic title for one figure.

    A picture is sent when the figure has png, jpeg, gif, or webp bytes.
    Otherwise the figure's text is sent. Nothing is stored. A refusal or a
    blank title returns an empty string.
    """
    text, media, media_type = figure_message(section)
    return ask_for_figure_title(text, media=media, media_type=media_type, model=model)


def ask_for_figure_title(
    text: str,
    *,
    media: bytes | None = None,
    media_type: str | None = None,
    model: str = DEFAULT_MODEL,
) -> str:
    """Ask for a short topic title for one figure.

    ``text`` is the label or the table. ``media`` is the picture bytes when
    there is one. An empty figure makes no request. A refusal or a blank
    title returns "".
    """
    if not text.strip() and not media:
        return ""
    response = _require_client().chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": _FIGURE_INSTRUCTIONS},
            {"role": "user", "content": _user_content(text, media, media_type)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "figure_title",
                "strict": True,
                "schema": _FIGURE_SCHEMA,
            },
        },
    )
    return _read_title(response)


def read_figure_title(content: str | None, refusal: str | None = None) -> str:
    """Return the topic from a figure-title reply.

    A refusal, an empty reply, a reply that is not JSON, or a title that is
    not text returns "".
    """
    if refusal or not content:
        return ""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return ""
    if not isinstance(parsed, dict):
        return ""
    title = parsed.get("title")
    if not isinstance(title, str):
        return ""
    return title.strip()


def _user_content(
    text: str, media: bytes | None, media_type: str | None
) -> str | list[dict]:
    if not media:
        return text
    parts: list[dict] = []
    if text:
        parts.append({"type": "text", "text": text})
    encoded = base64.b64encode(media).decode("ascii")
    mime = media_type or "image/png"
    parts.append(
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}
    )
    return parts


def _read_title(response) -> str:
    message = response.choices[0].message
    return read_figure_title(message.content, message.refusal)


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


def _number_window(
    window: list[str], headings: list[list[str]] | None = None
) -> str:
    """Number one batch from 0. These sentences are already split."""
    return numbered_lines(window, headings)


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
    sentences: list[str],
    *,
    headings: list[list[str]] | None = None,
    window_size: int = WINDOW_SENTENCES,
) -> list[tuple[int, str]]:
    """Return checked ``(start, title)`` pairs for the whole document.

    A document shorter than one batch is a single call, and every cut is
    saved. Longer documents continue from the unsaved last cut. ``headings``
    is one path per sentence, written above the first sentence of each path.
    """
    if not sentences:
        return []
    collected: list[tuple[int, str]] = []
    seen: set[int] = set()
    cursor = 0
    while cursor < len(sentences):
        window = sentences[cursor : cursor + window_size]
        window_headings = headings[cursor : cursor + window_size] if headings is not None else None
        points = checked_splits(
            ask_for_splits(_number_window(window, window_headings)), len(window)
        )
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
