from ragbytes.chunk.registry import get_chunker
from ragbytes.chunk.semantic.hosted import chunk_semantic_hosted
from ragbytes.chunk.simple import chunk_simple
from ragbytes.chunk.structured import chunk_structured
from ragbytes.schemas import Section


def test_simple_is_registered_as_basic():
    assert get_chunker("basic") is chunk_simple
    assert get_chunker("semantic") is chunk_semantic_hosted


def test_each_chunk_has_its_own_id():
    section = Section(file_id="file-1", index=0, kind="text", data="n" * 4500)

    chunks = chunk_simple([section], filename="notes.txt")

    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    assert all(chunk.chunk_id != section.id for chunk in chunks)


def test_short_section_keeps_its_metadata_and_text():
    section = Section(
        file_id="file-1",
        index=3,
        kind="text",
        headings=["Guide", "Setup"],
        heading="Guide",
        subheading="Setup",
        page=2,
        data="Install the package.",
    )

    chunks = chunk_simple([section], filename="guide.txt")

    assert len(chunks) == 1
    assert chunks[0].content == "Guide\nSetup\n\nInstall the package."
    metadata = chunks[0].metadata
    assert metadata.filename == "guide.txt"
    assert metadata.file_id == "file-1"
    assert metadata.chunk_number == 0
    assert metadata.headings == ["Guide", "Setup"]
    assert metadata.heading == "Guide"
    assert metadata.subheading == "Setup"
    assert metadata.page == 2
    assert metadata.format == "text"
    assert (metadata.details.start, metadata.details.end) == (0, len(chunks[0].content))
    assert metadata.media_type is None


def _keeps_words_whole(chunks: list, original: str) -> None:
    assert "".join(chunk.content for chunk in chunks) == original
    for earlier, later in zip(chunks, chunks[1:]):
        assert earlier.content[-1].isspace() or later.content[0].isspace()


def test_text_is_cut_about_every_500_characters_without_overlap():
    text = f"{'word ' * 280}\n\n{'tail ' * 80}"
    section = Section(file_id="file-1", index=0, kind="text", heading="Guide", data=text)

    chunks = chunk_simple([section], filename="guide.txt")
    plain = text.strip()

    _keeps_words_whole(chunks, plain)
    assert len(chunks) > 1
    assert [chunk.metadata.chunk_number for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].metadata.heading == "Guide"
    assert section.data == text


def test_a_sentence_that_would_pass_500_starts_the_next_chunk():
    opening = "A. " * 166
    moved = "This sentence moves."
    text = opening + moved
    section = Section(file_id="file-1", index=0, kind="text", data=text)

    chunks = chunk_simple([section], filename="notes.txt")

    assert [chunk.content for chunk in chunks] == [opening, moved]
    assert len(chunks[0].content) == 498


def test_a_short_sentence_stays_when_it_still_fits():
    text = ("A. " * 160) + "Fits."
    section = Section(file_id="file-1", index=0, kind="text", data=text)

    chunks = chunk_simple([section], filename="notes.txt")

    assert [chunk.content for chunk in chunks] == [text]


def test_a_long_sentence_splits_at_the_word_boundary_closest_to_500():
    text = ("ab " * 156) + ("x" * 40) + " tail."
    section = Section(file_id="file-1", index=0, kind="text", data=text)

    chunks = chunk_simple([section], filename="notes.txt")

    assert [chunk.content for chunk in chunks] == [text[:508], " tail."]
    assert len(chunks[0].content) == 508


def test_a_sentence_just_past_500_stays_whole_when_its_end_is_closer():
    text = ("word " * 99) + "boundary"
    section = Section(file_id="file-1", index=0, kind="text", data=text)

    chunks = chunk_simple([section], filename="notes.txt")

    assert [chunk.content for chunk in chunks] == [text]
    assert len(chunks[0].content) == 503


def test_a_word_whose_start_is_closer_to_500_moves_to_the_next_chunk():
    text = ("ab " * 164) + "abcd " + ("y" * 30) + " end."
    section = Section(file_id="file-1", index=0, kind="text", data=text)

    chunks = chunk_simple([section], filename="notes.txt")

    assert chunks[0].content == text[:497]
    assert chunks[1].content == ("y" * 30) + " end."


def test_a_word_longer_than_the_limit_stays_whole():
    text = "n" * 4500
    section = Section(file_id="file-1", index=0, kind="text", data=text)

    chunks = chunk_simple([section], filename="notes.txt")

    assert [chunk.content for chunk in chunks] == [text]


def test_charts_images_and_complex_regions_stay_whole():
    picture = b"\x89PNG\r\n"
    for kind in ("chart", "image", "complex"):
        section = Section(
            file_id="file-1",
            index=0,
            kind=kind,
            data="x" * 3000,
            media=picture if kind in {"image", "complex"} else None,
            media_type="image/png" if kind in {"image", "complex"} else None,
        )

        chunks = chunk_simple([section], filename="notes.pdf")

        assert len(chunks) == 1
        assert chunks[0].metadata.format == kind
        assert chunks[0].metadata.details.end == 3000
        if kind in {"image", "complex"}:
            assert chunks[0].content == picture
            assert chunks[0].metadata.media_type == "image/png"
        else:
            assert chunks[0].content == "x" * 3000
            assert chunks[0].metadata.media_type is None
        assert section.media == (picture if kind in {"image", "complex"} else None)


def test_a_table_is_cut_every_500_characters():
    rows = [f"| row {index} | {'v' * 60} |" for index in range(60)]
    data = "\n".join(["Table 1 Sizes", "| Name | Value |", "| --- | --- |", *rows])
    section = Section(file_id="file-1", index=0, kind="table", heading="Guide", data=data)

    chunks = chunk_simple([section], filename="guide.pdf")

    _keeps_words_whole(chunks, data)
    assert len(chunks) > 1
    assert all(chunk.metadata.format == "table" for chunk in chunks)
    assert all(chunk.metadata.heading == "Guide" for chunk in chunks)
    assert not chunks[1].content.startswith("Table 1 Sizes")
    assert section.data == data


def test_short_sections_with_different_headings_share_a_chunk():
    sections = [
        Section(index=0, kind="text", headings=["Overview"], heading="Overview", page=1, data="Alpha."),
        Section(index=1, kind="text", headings=["Kit"], heading="Kit", page=2, data="Beta."),
    ]

    chunks = chunk_simple(sections, filename="notes.txt")

    assert len(chunks) == 1
    assert chunks[0].content == "Overview\n\nAlpha.\n\nKit\n\nBeta."
    assert chunks[0].metadata.heading == "Overview"
    assert chunks[0].metadata.page == 1
    assert chunks[0].embed_text == chunks[0].content


def test_a_cut_continues_into_the_next_heading():
    first = "a" * 420
    second = "b" * 200
    sections = [
        Section(index=0, kind="text", headings=["One"], heading="One", data=first),
        Section(index=1, kind="text", headings=["Two"], heading="Two", data=second),
    ]

    chunks = chunk_simple(sections, filename="notes.txt")
    joined = f"One\n\n{first}\n\nTwo\n\n{second}"

    assert [chunk.content for chunk in chunks] == [joined[: len(joined) - len(second)], second]
    assert chunks[0].metadata.heading == "One"
    assert "\nTwo\n" in chunks[0].content
    assert chunks[1].metadata.heading == "Two"
    assert chunks[1].content == second


def test_a_label_before_a_figure_moves_onto_the_figure():
    picture = b"\x89PNG\r\n"
    sections = [
        Section(index=0, kind="text", headings=["Guide"], page=1, data="Some sentence first."),
        Section(index=1, kind="text", headings=["Guide"], page=1, data="[ Component Direction ]"),
        Section(
            index=2,
            kind="image",
            headings=["Guide"],
            page=1,
            data="[Image: Chip placement]",
            media=picture,
            media_type="image/png",
        ),
        Section(index=3, kind="text", headings=["Guide"], page=1, data="(Bad Example) (Good Example)"),
    ]

    chunks = chunk_simple(sections, filename="sheet.pdf")

    assert [chunk.metadata.format for chunk in chunks] == ["text", "image", "text"]
    assert chunks[0].content == "Guide\n\nSome sentence first."
    assert chunks[1].content == picture
    assert chunks[1].embed_text == "Guide\n\n[ Component Direction ]\n[Image: Chip placement]"
    assert chunks[2].content == "(Bad Example) (Good Example)"


def test_a_figure_with_no_description_is_left_out():
    picture = b"\x89PNG\r\n"
    sections = [
        Section(index=0, kind="text", headings=["Guide"], page=1, data="Before the picture."),
        Section(index=1, kind="image", headings=["Guide"], page=1, data="[Image]", media=picture),
        Section(index=2, kind="chart", headings=["Guide"], page=1, data="[Chart]"),
        Section(index=3, kind="text", headings=["Guide"], page=1, data="After the picture."),
        Section(index=4, kind="text", headings=["Guide"], page=1, data="Pressurization Method"),
        Section(index=5, kind="image", headings=["Guide"], page=1, data="[Image]", media=picture),
    ]

    chunks = chunk_simple(sections, filename="sheet.pdf")

    assert [chunk.metadata.format for chunk in chunks] == ["text", "image"]
    assert chunks[0].content == "Guide\n\nBefore the picture.\n\nAfter the picture."
    assert chunks[1].content == picture
    assert chunks[1].embed_text == "Guide\n\nPressurization Method\n[Image]"


def test_a_complex_region_with_no_text_is_left_out():
    region = b"\x89PNG\r\n"
    sections = [
        Section(index=0, kind="text", headings=["Guide"], page=1, data="Readable page."),
        Section(index=1, kind="complex", headings=["Guide"], page=2, data="[Complex]", media=region),
    ]

    assert [chunk.content for chunk in chunk_simple(sections, filename="scan.pdf")] == [
        "Guide\n\nReadable page."
    ]
    assert [chunk.content for chunk in chunk_structured(sections, filename="scan.pdf")] == ["Readable page."]


def test_a_heading_is_written_once_for_the_sections_under_it():
    sections = [
        Section(index=0, kind="text", headings=["Guide", "Install"], heading="Guide", data="Run it."),
        Section(index=1, kind="text", headings=["Guide", "Install"], heading="Guide", data="Then check it."),
        Section(index=2, kind="text", headings=["Guide", "Configure"], heading="Guide", data="Edit it."),
    ]

    chunks = chunk_simple(sections, filename="guide.txt")

    assert chunks[0].content == "Guide\nInstall\n\nRun it.\n\nThen check it.\n\nConfigure\n\nEdit it."


def test_a_long_list_is_cut_every_500_characters():
    items = [f"- item {index} " + "w" * 90 for index in range(40)]
    data = "\n".join(items)
    section = Section(index=0, kind="list", data=data)

    chunks = chunk_simple([section], filename="notes.md")

    _keeps_words_whole(chunks, data)
    assert len(chunks) > 1
    assert all(chunk.metadata.format == "list" for chunk in chunks)


def test_long_code_without_spaces_stays_one_chunk():
    section = Section(file_id="file-1", index=0, kind="code", data="n" * 2500)

    chunks = chunk_simple([section], filename="app.py")

    assert [chunk.content for chunk in chunks] == ["n" * 2500]
    assert chunks[0].metadata.format == "code"


def test_offsets_follow_sections_in_file_order():
    later = Section(file_id="file-1", index=1, kind="text", data="Hello.")
    earlier = Section(file_id="file-1", index=0, kind="text", data="n" * 4500)
    document = "n" * 4500 + "\n\nHello."

    chunks = chunk_simple([later, earlier], filename="notes.txt")
    joined = "\n\n".join(chunk.content for chunk in chunks)

    assert [chunk.content for chunk in chunks] == ["n" * 4500, "\n\nHello."]
    assert [chunk.metadata.chunk_number for chunk in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        start = chunk.metadata.details.start
        end = chunk.metadata.details.end
        assert joined[start:end] == chunk.content
        assert chunk.metadata.chunk_number == chunks.index(chunk)


def test_blank_sections_are_skipped():
    blank = Section(index=0, kind="text", data="  ")
    kept = Section(index=1, kind="text", data="Kept.")

    chunks = chunk_simple([blank, kept], filename="notes.txt")

    assert [chunk.content for chunk in chunks] == ["Kept."]
