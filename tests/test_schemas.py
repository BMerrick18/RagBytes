import base64

from ragbytes.schemas import Chunk, ChunkDetails, ChunkMetadata


def test_chunk_carries_file_and_section_metadata():
    item = Chunk(
        content="Install the package.",
        embed_text="Guide > Setup\n\nInstall the package.",
        metadata=ChunkMetadata(
            filename="guide.md",
            file_id="file-1",
            chunk_number=0,
            headings=["Guide", "Setup"],
            heading="Guide",
            subheading="Setup",
            page=2,
            format="text",
            details=ChunkDetails(start=12, end=33),
        ),
    )

    assert item.metadata.filename == "guide.md"
    assert item.metadata.file_id == "file-1"
    assert item.metadata.chunk_number == 0
    assert item.metadata.headings == ["Guide", "Setup"]
    assert item.metadata.heading == "Guide"
    assert item.metadata.subheading == "Setup"
    assert item.metadata.page == 2
    assert item.metadata.format == "text"
    assert item.metadata.details.start == 12
    assert item.metadata.details.end == 33
    assert item.content == "Install the package."
    assert item.embed_text == "Guide > Setup\n\nInstall the package."
    assert item.metadata.media_type is None
    assert item.chunk_id

    other = Chunk(content="Then run it.", embed_text="Then run it.", metadata=item.metadata)
    assert other.chunk_id != item.chunk_id


def test_image_chunk_encodes_its_content_as_base64():
    picture = b"\x89PNG\r\n"
    item = Chunk(
        content=picture,
        embed_text="[Image: Plot]",
        metadata=ChunkMetadata(
            filename="notes.pdf",
            file_id="file-1",
            chunk_number=0,
            format="image",
            media_type="image/png",
            details=ChunkDetails(start=0, end=13),
        ),
    )

    dumped = item.model_dump(mode="json")

    assert list(dumped) == ["chunk_id", "metadata", "embed_text", "content"]
    assert dumped["embed_text"] == "[Image: Plot]"
    assert base64.b64decode(dumped["content"]) == picture
    assert dumped["metadata"]["format"] == "image"
    assert dumped["metadata"]["media_type"] == "image/png"
    assert dumped["metadata"]["topic"] is None
    assert dumped["metadata"]["heading_paths"] == []
    assert dumped["metadata"]["pages"] == []
