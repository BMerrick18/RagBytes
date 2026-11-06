from ragbytes.chunk.semantic.semantic import chunk_semantic
from ragbytes.schemas import Section


class _Embedder:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        return [[0.0, 1.0] if "tariff" in text else [1.0, 0.0] for text in texts]


def _section(
    index: int,
    kind: str,
    data: str,
    headings: list[str],
    *,
    media: bytes | None = None,
) -> Section:
    return Section(
        file_id="file-1",
        index=index,
        kind=kind,
        headings=headings,
        heading=headings[0],
        subheading=headings[-1] if len(headings) > 1 else None,
        data=data,
        media=media,
        media_type="image/png" if media else None,
    )


def test_close_passages_under_one_heading_share_a_chunk():
    embedder = _Embedder()
    sections = [
        _section(0, "text", "Warm the lamp.", ["Guide", "Setup"]),
        _section(1, "text", "Read the meter.", ["Guide", "Setup"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert len(chunks) == 1
    assert chunks[0].content == "Warm the lamp.\n\nRead the meter."
    assert chunks[0].embed_text == "Guide > Setup\n\nWarm the lamp.\n\nRead the meter."
    assert chunks[0].metadata.heading == "Guide"
    assert chunks[0].metadata.subheading == "Setup"
    assert embedder.batches == [["Warm the lamp.", "Read the meter."]]


def test_a_drop_in_similarity_starts_a_new_chunk_under_the_same_heading():
    embedder = _Embedder()
    sections = [
        _section(0, "text", "Warm the lamp.", ["Guide", "Setup"]),
        _section(1, "text", "The tariff changed the quay.", ["Guide", "Setup"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert [chunk.content for chunk in chunks] == ["Warm the lamp.", "The tariff changed the quay."]
    assert [chunk.metadata.chunk_number for chunk in chunks] == [0, 1]
    assert {chunk.metadata.subheading for chunk in chunks} == {"Setup"}


def test_a_heading_change_is_a_boundary_before_any_comparison():
    embedder = _Embedder()
    sections = [
        _section(0, "text", "Run the installer.", ["Guide", "Install"]),
        _section(1, "text", "Edit the file.", ["Guide", "Configure"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert [chunk.content for chunk in chunks] == ["Run the installer.", "Edit the file."]
    assert [(chunk.metadata.heading, chunk.metadata.subheading) for chunk in chunks] == [
        ("Guide", "Install"),
        ("Guide", "Configure"),
    ]
    assert embedder.batches == []


def test_a_long_paragraph_is_split_where_its_sentences_change_subject():
    same = "The crew walked the pier and wrote down the reading. "
    changed = "The tariff closed the quay and the crew went home. "
    paragraph = same * 15 + changed * 8
    embedder = _Embedder()
    section = _section(0, "text", paragraph.strip(), ["Guide", "North Pier"])

    chunks = chunk_semantic([section], filename="notes.txt", embedder=embedder)

    assert len(chunks) == 2
    assert "tariff" not in chunks[0].content
    assert chunks[1].content.startswith("The tariff closed the quay")
    assert chunks[0].metadata.subheading == "North Pier"
    assert len(embedder.batches) == 2
    assert embedder.batches[0][0] == "The crew walked the pier and wrote down the reading."
    assert "tariff" in embedder.batches[1][1]


def test_both_passes_embed_every_heading_in_one_call():
    same = "The crew walked the pier and wrote down the reading. "
    changed = "The tariff closed the quay and the crew went home. "
    south = "Beta kept the lamp lit and wrote down the reading. "
    embedder = _Embedder()
    sections = [
        _section(0, "text", (same * 15 + changed * 8).strip(), ["Guide", "North"]),
        _section(1, "text", (south * 15 + changed * 8).strip(), ["Guide", "South"]),
    ]

    chunks = chunk_semantic(sections, filename="notes.txt", embedder=embedder)

    assert len(embedder.batches) == 2
    first, second = embedder.batches
    south_at = next(index for index, text in enumerate(first) if text.startswith("Beta"))
    assert first[0] == "The crew walked the pier and wrote down the reading."
    assert "tariff" in first[south_at - 1]
    assert first[-1].startswith("The tariff closed the quay")
    assert [text.startswith("Beta") or "tariff" in text for text in second] == [False, True, True, True]
    assert [chunk.metadata.subheading for chunk in chunks] == ["North", "North", "South", "South"]
    assert "Beta" not in chunks[0].content
    assert chunks[1].content.startswith("The tariff closed the quay")
    assert chunks[2].content.startswith("Beta kept the lamp lit")
    assert chunks[3].content.startswith("The tariff closed the quay")


def test_short_passages_from_every_heading_share_one_embedding_call():
    embedder = _Embedder()
    sections = [
        _section(0, "text", "Warm the lamp.", ["Guide", "Setup"]),
        _section(1, "text", "Read the meter.", ["Guide", "Setup"]),
        _section(2, "text", "Open the gate.", ["Guide", "Route"]),
        _section(3, "text", "The tariff changed the quay.", ["Guide", "Route"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert embedder.batches == [
        [
            "Warm the lamp.",
            "Read the meter.",
            "Open the gate.",
            "The tariff changed the quay.",
        ]
    ]
    assert [chunk.content for chunk in chunks] == [
        "Warm the lamp.\n\nRead the meter.",
        "Open the gate.",
        "The tariff changed the quay.",
    ]
    assert [chunk.metadata.subheading for chunk in chunks] == ["Setup", "Route", "Route"]


def test_an_image_keeps_its_bytes_when_it_is_its_own_chunk():
    picture = b"\x89PNG\r\n"

    class _FigureEmbedder(_Embedder):
        def embed(self, texts: list[str]) -> list[list[float]]:
            self.batches.append(list(texts))
            return [[0.0, 1.0] if text.startswith("[Image") else [1.0, 0.0] for text in texts]

    embedder = _FigureEmbedder()
    sections = [
        _section(0, "text", "Warm the lamp.", ["Guide", "Setup"]),
        _section(1, "image", "[Image: Wiring]", ["Guide", "Setup"], media=picture),
    ]

    chunks = chunk_semantic(sections, filename="guide.pdf", embedder=embedder)

    assert [chunk.metadata.format for chunk in chunks] == ["text", "image"]
    assert chunks[1].content == picture
    assert chunks[1].embed_text == "Guide > Setup\n\n[Image: Wiring]"
