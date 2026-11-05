from ragbytes.chunk.assemble import sections_for_chunking
from ragbytes.schemas import Section


def test_text_sections_keep_their_file_metadata():
    first = Section(
        file_id="file-1",
        index=0,
        kind="text",
        headings=["Guide"],
        heading="Guide",
        data="Install the package.",
    )
    second = Section(file_id="file-1", index=1, kind="text", heading="Guide", data="Then run it.")

    chunks = sections_for_chunking([second, first], filename="guide.txt")

    assert [item.content for item in chunks] == ["Install the package.", "Then run it."]
    assert [item.metadata.chunk_number for item in chunks] == [0, 1]
    assert chunks[0].metadata.file_id == "file-1"
    assert chunks[0].metadata.headings == ["Guide"]
    assert chunks[0].metadata.heading == "Guide"
    assert chunks[0].metadata.format == "text"
    assert (chunks[0].metadata.details.start, chunks[0].metadata.details.end) == (0, 20)
    assert (chunks[1].metadata.details.start, chunks[1].metadata.details.end) == (22, 34)


def test_image_chunk_content_is_the_picture():
    picture = b"\x89PNG\r\n\x1a\n"
    section = Section(
        file_id="file-1",
        index=4,
        kind="image",
        heading="Guide",
        page=2,
        data="[Image: Plot]",
        media=picture,
        media_type="image/png",
    )

    chunks = sections_for_chunking([section], filename="notes.pdf")

    assert chunks[0].content == picture
    assert chunks[0].metadata.chunk_number == 0
    assert chunks[0].metadata.format == "image"
    assert chunks[0].metadata.media_type == "image/png"
    assert chunks[0].metadata.page == 2
    assert (chunks[0].metadata.details.start, chunks[0].metadata.details.end) == (0, 13)
    assert section.media == picture


def test_metadata_labels_simple_and_complex_sections():
    simple = Section(index=0, kind="table", data="| A |\n| --- |")
    mixed = Section(
        index=1,
        kind="complex",
        data="[Complex]",
        media=b"<table>",
        media_type="text/html",
    )

    chunks = sections_for_chunking([mixed, simple], filename="notes.html")

    assert simple.complexity == "simple"
    assert mixed.complexity == "complex"
    assert [chunk.metadata.format for chunk in chunks] == ["table", "complex"]
    assert chunks[0].content == "| A |\n| --- |"
    assert chunks[0].metadata.media_type is None
    assert chunks[1].content == "<table>"
    assert chunks[1].metadata.media_type == "text/html"
