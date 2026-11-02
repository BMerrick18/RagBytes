from shark_byte.chunk.registry import get_chunker
from shark_byte.chunk.structured import chunk_structured
from shark_byte.schemas import Section


def _text(index: int, headings: list[str], data: str, page: int | None = None) -> Section:
    return Section(index=index, kind="text", headings=headings, page=page, data=data)


def test_structured_is_registered():
    assert get_chunker("structured") is chunk_structured


def test_one_heading_section_is_one_chunk_across_pages_and_around_a_figure():
    picture = b"\x89PNG\r\n"
    path = ["Guide", "Setup"]
    sections = [
        _text(0, path, "First paragraph. " * 20, page=1),
        Section(index=1, kind="image", headings=path, page=1, data="[Image: Wiring]", media=picture),
        _text(2, path, "Second paragraph. " * 20, page=2),
        Section(index=3, kind="list", headings=path, page=2, data="- One\n- Two"),
    ]

    chunks = chunk_structured(sections, filename="guide.pdf")

    assert [chunk.metadata.format for chunk in chunks] == ["text", "image"]
    text, image = chunks
    assert text.content == "\n\n".join(
        [("First paragraph. " * 20).strip(), ("Second paragraph. " * 20).strip(), "- One\n- Two"]
    )
    assert text.metadata.headings == path
    assert text.metadata.page == 1
    assert image.content == picture


def test_a_short_subheading_stays_its_own_chunk():
    sections = [
        _text(0, ["Guide", "Install"], "Run the installer."),
        _text(1, ["Guide", "Configure"], "Edit the settings file."),
        _text(2, ["Guide", "Configure", "Advanced"], "Turn on logging."),
    ]

    chunks = chunk_structured(sections, filename="guide.md")

    assert [(chunk.metadata.heading, chunk.metadata.subheading) for chunk in chunks] == [
        ("Guide", "Install"),
        ("Guide", "Configure"),
        ("Guide", "Advanced"),
    ]
    assert [chunk.metadata.headings for chunk in chunks] == [
        ["Guide", "Install"],
        ["Guide", "Configure"],
        ["Guide", "Configure", "Advanced"],
    ]
    assert chunks[2].content == "Turn on logging."
    assert chunks[2].embed_text == "Guide > Configure > Advanced\n\nTurn on logging."


def test_sections_under_different_parents_stay_apart():
    sections = [
        _text(0, ["Guide", "Install"], "Run the installer."),
        _text(1, ["Reference", "Options"], "Every option is listed here."),
    ]

    chunks = chunk_structured(sections, filename="guide.md")

    assert [chunk.metadata.headings for chunk in chunks] == [["Guide", "Install"], ["Reference", "Options"]]


def test_two_substantial_siblings_stay_apart():
    long_install = "Install step. " * 50
    long_configure = "Configure step. " * 50
    sections = [
        _text(0, ["Guide", "Install"], long_install),
        _text(1, ["Guide", "Configure"], long_configure),
    ]

    chunks = chunk_structured(sections, filename="guide.md")

    assert [chunk.metadata.headings for chunk in chunks] == [["Guide", "Install"], ["Guide", "Configure"]]


def test_a_short_opening_stays_apart_from_its_subsection():
    sections = [
        _text(0, ["Linux", "Overview"], "Overview text. " * 80),
        _text(1, ["Linux", "History"], "Main articles: History of Linux."),
        _text(2, ["Linux", "History", "Precursors"], "Unix was conceived in 1969. " * 20),
    ]

    chunks = chunk_structured(sections, filename="linux.html")

    assert [chunk.metadata.headings for chunk in chunks] == [
        ["Linux", "Overview"],
        ["Linux", "History"],
        ["Linux", "History", "Precursors"],
    ]
    assert chunks[1].content == "Main articles: History of Linux."
    assert chunks[1].metadata.subheading == "History"
    assert chunks[2].metadata.subheading == "Precursors"


def test_a_long_section_splits_evenly_between_its_paragraphs():
    paragraphs = [(f"Paragraph {index}. " + "word " * 100).strip() for index in range(10)]
    sections = [_text(index, ["Guide"], paragraph) for index, paragraph in enumerate(paragraphs)]

    chunks = chunk_structured(sections, filename="guide.md")

    sizes = [len(chunk.content) for chunk in chunks]
    assert len(chunks) == 4
    assert all(size <= 2000 for size in sizes)
    assert max(sizes) - min(sizes) < 600
    assert "\n\n".join(chunk.content for chunk in chunks) == "\n\n".join(paragraphs)
    assert all(chunk.metadata.headings == ["Guide"] for chunk in chunks)


def _last_sentence(text: str) -> str:
    begin = 0
    index = 0
    while index < len(text):
        if text[index] in ".!?" and index + 1 < len(text) and text[index + 1].isspace():
            nxt = index + 1
            while nxt < len(text) and text[nxt].isspace():
                nxt += 1
            if nxt < len(text):
                begin = nxt
            index = nxt
            continue
        index += 1
    return text[begin:]


def test_a_paragraph_split_in_two_overlaps_by_one_sentence():
    sentences = []
    for index in range(50):
        if index % 3 == 0:
            sentences.append(f"Step {index:02d} packs the bearings before you ship the unit.")
        elif index % 3 == 1:
            sentences.append(f"Step {index:02d} checks the housing once the press is set!")
        else:
            sentences.append(f"Step {index:02d} asks whether the seal is seated?")
    paragraph = " ".join(sentences)
    sections = [_text(0, ["Guide"], paragraph)]

    chunks = chunk_structured(sections, filename="guide.md")

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 2000 for chunk in chunks)
    rebuilt = chunks[0].content
    for earlier, later in zip(chunks, chunks[1:]):
        overlap = _last_sentence(earlier.content)
        assert overlap != earlier.content
        assert ". " not in overlap and "! " not in overlap and "? " not in overlap
        assert later.content.startswith(overlap)
        rebuilt = f"{rebuilt} {later.content[len(overlap):].lstrip()}"
    assert rebuilt == paragraph


def test_a_split_between_paragraphs_does_not_repeat_a_sentence():
    first = " ".join(f"Opening {index:02d} stays in the first paragraph." for index in range(40))
    second = " ".join(f"Closing {index:02d} stays in the second paragraph." for index in range(12))
    assert 1600 <= len(first) < 2000
    assert len(first) + 2 + len(second) > 2000
    sections = [_text(0, ["Guide"], f"{first}\n\n{second}")]

    chunks = chunk_structured(sections, filename="guide.md")

    assert [chunk.content for chunk in chunks] == [first, second]


def test_a_long_last_sentence_overlaps_by_about_200_characters():
    paragraph = "Short intro. " + " ".join(f"w{index:03d}" for index in range(600))
    sections = [_text(0, ["Guide"], paragraph)]

    chunks = chunk_structured(sections, filename="guide.md")

    assert len(chunks) == 2
    first, second = (chunk.content for chunk in chunks)
    shared = next(size for size in range(len(second), 0, -1) if first.endswith(second[:size]))
    assert 150 <= shared <= 250


def test_a_paragraph_without_a_sentence_still_splits():
    paragraph = "word " * 800
    sections = [_text(0, ["Guide"], paragraph)]

    chunks = chunk_structured(sections, filename="guide.md")

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 2000 for chunk in chunks)
    assert " ".join(chunk.content for chunk in chunks) == paragraph.strip()
