"""Split a document into fixed-size character windows."""

from ragbytes.chunk.assemble import sections_for_chunking, titled_path
from ragbytes.schemas import Chunk, Section

CHUNK_SIZE = 500
CHUNK_OVERLAP = 200
SENTENCE_OVERLAP_LIMIT = 300
_LOOKBACK = 400
_WORD_SLACK = 40
_LABEL_LIMIT = 100
WHOLE_KINDS = frozenset({"chart", "complex", "image"})
_PACKED_KINDS = frozenset({"text", "list"})
_LABELLED_KINDS = frozenset({"image", "chart", "table"})
_BARE_MARKERS = frozenset({"[Image]", "[Chart]", "[Complex]"})
_BREAKS = ("\n\n", "\n- ", "\n", ". ", "! ", "? ", " ")


def chunk_simple(sections: list[Section], *, filename: str) -> list[Chunk]:
    """Cut the document every 500 characters, ignoring heading boundaries.

    Text, lists, tables, and code are joined in file order and split about
    every 500 characters. A heading is written into that text where it begins,
    so it stays visible inside whichever window it falls in, but a heading or
    subheading change does not start a chunk. A sentence that would pass 500
    characters starts the next chunk. A sentence longer than 500 characters is
    split at the word boundary closest to 500. A word is never divided, and a
    word longer than 500 characters stays whole. There is no overlap. The last
    piece of a run is shorter when the text does not fill it. Each piece keeps
    the metadata of the section where it starts.

    A short label such as ``[ Component Direction ]``, or a lone list item
    such as ``Minimum Quantity``, just before an image or chart on the same
    page under the same headings is written above that figure. An image or
    chart with no description or label is left out, since its marker alone
    says nothing to embed, and so is a complex region no reader has turned
    into text yet. Images, charts, and complex regions stay whole and are not
    mixed into the character windows.

    ``chunk_number`` counts the returned chunks from 0. ``content`` is the
    chunk text, or the original bytes when a whole section is an image or a
    complex region. ``metadata.format`` says which kind the piece starts in.
    ``start`` and ``end`` are offsets into the chunk texts joined by a blank line.
    """
    pieces: list[Section] = []
    pending: list[tuple[Section, str]] = []
    previous: list[str] | None = None

    def flush() -> None:
        pieces.extend(_character_windows(pending))
        pending.clear()

    for section in prepared_sections(sections):
        text = section.data.strip()
        if not text:
            continue
        if section.kind in WHOLE_KINDS:
            flush()
            pieces.append(section)
            previous = window_path(section)
            continue
        pending.append((section, section_window_text(section, previous)))
        previous = window_path(section)
    flush()
    return sections_for_chunking(pieces, filename=filename, exact=True)


def prepared_sections(sections: list[Section]) -> list[Section]:
    """Sort into file order, write figure labels onto their figures, and drop bare figure and complex markers."""
    ordered = _with_labels(sorted(sections, key=lambda item: item.index))
    return [section for section in ordered if section.data.strip() not in _BARE_MARKERS]


def _with_labels(sections: list[Section]) -> list[Section]:
    """Write a short label that sits just before a figure above that figure's marker."""
    kept: list[Section] = []
    index = 0
    while index < len(sections):
        section = sections[index]
        following = sections[index + 1] if index + 1 < len(sections) else None
        if following is not None and _is_label_for(section, following):
            kept.append(
                following.model_copy(
                    update={"data": f"{_label_text(section)}\n{following.data.strip()}"}
                )
            )
            index += 2
            continue
        kept.append(section)
        index += 1
    return kept


def _is_label_for(section: Section, following: Section) -> bool:
    """A one-line title-like text, or a lone list item, just before a figure or table."""
    if section.kind not in _PACKED_KINDS or following.kind not in _LABELLED_KINDS:
        return False
    if not _same_place(section, following):
        return False
    text = _label_text(section)
    if not text or len(text) > _LABEL_LIMIT or "\n" in text:
        return False
    return not text.endswith((".", "!", "?", ":", ";", ","))


def _label_text(section: Section) -> str:
    text = section.data.strip()
    if section.kind == "list" and text.startswith("- "):
        return text[2:].strip()
    return text


def section_window_text(section: Section, previous: list[str] | None) -> str:
    """Return this section's text, with heading lines for titles that start here.

    ``previous`` is the earlier section's ``window_path``. A heading already
    written for an earlier section is not repeated. New titles are one per
    line, then a blank line, then the section text.
    """
    text = section.data.strip()
    fresh = _fresh_headings(window_path(section), previous)
    if not fresh:
        return text
    block = "\n".join(fresh)
    return f"{block}\n\n{text}" if text else block


def window_path(section: Section) -> list[str]:
    """The document title and heading path that are written into the windows."""
    return titled_path(section.title, section.headings)


def _fresh_headings(headings: list[str], previous: list[str] | None) -> list[str]:
    """Return the tail of ``headings`` that ``previous`` does not already include."""
    titles = [heading for heading in headings if heading]
    if not previous:
        return titles
    shared = 0
    for left, right in zip(previous, titles):
        if left != right:
            break
        shared += 1
    return titles[shared:]


def _window_end(text: str, start: int, limit: int = CHUNK_SIZE) -> int:
    """End this window on a sentence boundary, or the word boundary nearest the limit.

    Whole sentences stay together. A sentence that would pass ``limit`` characters
    starts the next window. A sentence longer than the limit is split at the word
    boundary closest to the limit. A word is a run of non-whitespace, and a word
    longer than the limit stays whole.
    """
    if start >= len(text) or len(text) - start <= limit:
        return len(text) if start < len(text) else start
    cursor = start
    while cursor < len(text):
        sentence_end = _sentence_end(text, cursor)
        if sentence_end <= cursor:
            return len(text)
        if sentence_end - start > limit:
            if cursor == start:
                return _closest_word_boundary(text, start, sentence_end, start + limit)
            return cursor
        cursor = sentence_end
    return cursor


def _sentence_end(text: str, start: int) -> int:
    """Return the index where the next sentence starts, including this sentence's trailing space."""
    index = start
    length = len(text)
    while index < length:
        if text[index] in ".!?":
            nxt = index + 1
            if nxt >= length or text[nxt].isspace():
                while nxt < length and text[nxt].isspace():
                    nxt += 1
                return nxt
        index += 1
    return length


def _closest_word_boundary(text: str, start: int, stop: int, target: int) -> int:
    """Return the cut in ``(start, stop]`` nearest ``target`` that does not divide a word.

    A cut may sit at the end of the sentence, on either side of whitespace, or
    between a word and the space beside it. When two cuts are equally close, the
    one at or before ``target`` wins. A span with no internal boundary stays whole.
    """
    best = stop
    best_key = (abs(stop - target), stop > target)
    for index in range(start + 1, stop):
        if not text[index - 1].isspace() and not text[index].isspace():
            continue
        key = (abs(index - target), index > target)
        if key < best_key:
            best = index
            best_key = key
    return best


def _character_windows(parts: list[tuple[Section, str]]) -> list[Section]:
    """Cut joined section text into windows of about ``CHUNK_SIZE`` characters."""
    if not parts:
        return []
    full = "\n\n".join(text for _, text in parts)
    owners: list[Section] = []
    for index, (section, text) in enumerate(parts):
        if index:
            owners.extend([section] * 2)
        owners.extend([section] * len(text))
    pieces: list[Section] = []
    start = 0
    while start < len(full):
        end = _window_end(full, start)
        pieces.append(
            owners[start].model_copy(update={"data": full[start:end], "media": None, "media_type": None})
        )
        start = end
    return pieces


def _same_place(first: Section, second: Section) -> bool:
    return first.headings == second.headings and first.page == second.page


def piece_texts(section: Section, *, limit: int, sentence_overlap: bool = False) -> list[str]:
    """Split one section's text to fit ``limit``. Figures and complex regions stay whole.

    With ``sentence_overlap``, a paragraph cut in two repeats its last sentence in the
    next piece. Otherwise the next piece repeats about 200 characters.
    """
    text = section.data.strip()
    if not text:
        return []
    if section.kind in WHOLE_KINDS or len(text) <= limit:
        return [text]
    if section.kind == "table":
        return _split_table(text, limit)
    return _split_text(text, limit, sentence_overlap=sentence_overlap)


def _split_table(text: str, limit: int) -> list[str]:
    """Split a markdown table between rows, repeating its lead-in and header."""
    lines = text.split("\n")
    first_row = next((index for index, line in enumerate(lines) if line.startswith("|")), None)
    if first_row is None or first_row + 2 > len(lines):
        return [text]
    head = lines[: first_row + 2]
    body = lines[first_row + 2 :]
    head_size = sum(len(line) + 1 for line in head)
    if not body or head_size >= limit:
        return [text]
    pieces: list[str] = []
    current: list[str] = []
    size = head_size
    for line in body:
        if current and size + len(line) + 1 > limit:
            pieces.append("\n".join(head + current))
            current = []
            size = head_size
        current.append(line)
        size += len(line) + 1
    if current:
        pieces.append("\n".join(head + current))
    return pieces


def _split_text(text: str, limit: int, *, sentence_overlap: bool = False) -> list[str]:
    pieces: list[str] = []
    start = 0
    while start < len(text):
        if len(text) - start <= limit:
            tail = text[start:].strip()
            if tail:
                pieces.append(tail)
            break
        end = _break_end(text, start, limit)
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if sentence_overlap:
            nxt = _sentence_overlap_start(text, start, end)
        else:
            nxt = _overlap_start(text, start, end)
        start = end if nxt <= start else nxt
    return pieces


def _break_end(text: str, start: int, limit: int) -> int:
    """End this chunk on a nearby break, or on the size limit."""
    limit = start + limit
    window_start = limit - _LOOKBACK
    window = text[window_start:limit]
    for separator in _BREAKS:
        found = window.rfind(separator)
        if found != -1:
            # A break on a newline ends just after it, so a list item keeps its marker.
            consumed = 1 if separator.startswith("\n") else len(separator)
            return window_start + found + consumed
    return limit


def _sentence_overlap_start(text: str, start: int, end: int) -> int:
    """Begin the next piece at the last sentence, when this cut is inside a paragraph.

    A cut on a blank line leaves the next paragraph whole. A paragraph with no
    earlier sentence keeps going from the cut, so a piece always moves forward.
    A last sentence longer than about 300 characters would repeat most of the
    piece, so the next piece repeats about 200 characters instead.
    """
    if 0 < end < len(text) and text[end - 1] == "\n" and text[end] == "\n":
        return end
    begin = _last_sentence_begin(text[start:end])
    if begin <= 0:
        return end
    if end - (start + begin) > SENTENCE_OVERLAP_LIMIT:
        return _overlap_start(text, start, end)
    return start + begin


def _last_sentence_begin(window: str) -> int:
    """Offset where the last sentence in ``window`` starts, or 0 when it is the only one."""
    begin = 0
    index = 0
    length = len(window)
    while index < length:
        if window[index] in ".!?":
            nxt = index + 1
            if nxt < length and window[nxt].isspace():
                while nxt < length and window[nxt].isspace():
                    nxt += 1
                if nxt < length and window[nxt:].strip():
                    begin = nxt
                index = nxt
                continue
        index += 1
    return begin


def _overlap_start(text: str, start: int, end: int) -> int:
    """Begin the next chunk about 200 characters back, on a word boundary."""
    overlap = end - CHUNK_OVERLAP
    if overlap <= start:
        return end
    if text[overlap - 1].isspace():
        return overlap
    snapped = overlap
    floor = max(start, overlap - _WORD_SLACK)
    while snapped > floor and not text[snapped - 1].isspace():
        snapped -= 1
    if snapped > start and text[snapped - 1].isspace():
        return snapped
    return overlap
