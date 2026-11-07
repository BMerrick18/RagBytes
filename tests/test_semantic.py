from ragbytes.chunk.semantic.semantic import chunk_semantic
from ragbytes.chunk.semantic.styles import BALANCED, resolve_style
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
        heading=headings[0] if headings else None,
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


# Passages long enough to stand as chunks on their own, so a cut between them is kept.
_LAMP = (
    "Warm the lamp before the crew arrives, then check the wick and the glass "
    "so the light carries across the water to the far pier."
)
_TARIFF = (
    "The tariff changed the quay fees for every vessel this season, and the "
    "harbour office posted the new rates on the gate by the lock."
)
_INSTALL = (
    "Run the installer from the mounted image, accept the defaults, and let it "
    "finish before you unplug the drive or close the lid."
)


def test_a_drop_in_similarity_starts_a_new_chunk_under_the_same_heading():
    embedder = _Embedder()
    sections = [
        _section(0, "text", _LAMP, ["Guide", "Setup"]),
        _section(1, "text", _TARIFF, ["Guide", "Setup"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert [chunk.content for chunk in chunks] == [_LAMP, _TARIFF]
    assert [chunk.metadata.chunk_number for chunk in chunks] == [0, 1]
    assert {chunk.metadata.subheading for chunk in chunks} == {"Setup"}


def test_a_tiny_closing_sentence_joins_its_paragraph_despite_a_low_score():
    embedder = _Embedder()
    sections = [
        _section(0, "text", _LAMP, ["Guide", "Setup"]),
        _section(1, "text", "The tariff is discussed in a separate memo.", ["Guide", "Setup"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert [chunk.content for chunk in chunks] == [f"{_LAMP}\n\nThe tariff is discussed in a separate memo."]


_LONG = "Run the installer and wait for it to finish before you continue. " * 4


def test_a_heading_change_between_larger_headings_is_a_boundary_before_any_comparison():
    embedder = _Embedder()
    sections = [
        _section(0, "text", _LONG.strip(), ["Guide", "Install"]),
        _section(1, "text", _LONG.strip(), ["Guide", "Configure"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert [chunk.content for chunk in chunks] == [_LONG.strip(), _LONG.strip()]
    assert [(chunk.metadata.heading, chunk.metadata.subheading) for chunk in chunks] == [
        ("Guide", "Install"),
        ("Guide", "Configure"),
    ]
    assert embedder.batches == []


def test_small_sibling_headings_share_a_chunk_under_their_parent():
    embedder = _Embedder()
    sections = [
        _section(0, "text", "Run the installer.", ["Guide", "Install"]),
        _section(1, "text", "Edit the file.", ["Guide", "Configure"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert [chunk.content for chunk in chunks] == ["Install\n\nRun the installer.\n\nConfigure\n\nEdit the file."]
    assert chunks[0].metadata.headings == ["Guide"]
    assert (chunks[0].metadata.heading, chunks[0].metadata.subheading) == ("Guide", None)
    assert chunks[0].embed_text == "Guide\n\nInstall\n\nRun the installer.\n\nConfigure\n\nEdit the file."
    assert embedder.batches == [["Run the installer.", "Edit the file."]]


def test_small_outermost_headings_keep_their_own_chunks_and_paths():
    embedder = _Embedder()
    sections = [
        _section(0, "text", "Run the installer.", ["Install"]),
        _section(1, "text", "Edit the file.", ["Configure"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert [chunk.content for chunk in chunks] == ["Run the installer.", "Edit the file."]
    assert [chunk.metadata.headings for chunk in chunks] == [["Install"], ["Configure"]]
    assert [chunk.metadata.heading for chunk in chunks] == ["Install", "Configure"]
    assert [chunk.embed_text for chunk in chunks] == ["Install\n\nRun the installer.", "Configure\n\nEdit the file."]
    assert embedder.batches == []


def test_unrelated_small_siblings_keep_their_own_headings():
    embedder = _Embedder()
    sections = [
        _section(0, "text", _INSTALL, ["Guide", "Install"]),
        _section(1, "text", _TARIFF, ["Guide", "Harbour"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert [chunk.content for chunk in chunks] == [_INSTALL, _TARIFF]
    assert [chunk.metadata.headings for chunk in chunks] == [["Guide", "Install"], ["Guide", "Harbour"]]


def test_strict_headings_keep_small_siblings_apart():
    embedder = _Embedder()
    sections = [
        _section(0, "text", "Run the installer.", ["Guide", "Install"]),
        _section(1, "text", "Edit the file.", ["Guide", "Configure"]),
    ]

    chunks = chunk_semantic(
        sections, filename="guide.txt", embedder=embedder, style=resolve_style(strict_headings=True)
    )

    assert [chunk.content for chunk in chunks] == ["Run the installer.", "Edit the file."]
    assert [chunk.metadata.headings for chunk in chunks] == [["Guide", "Install"], ["Guide", "Configure"]]
    assert embedder.batches == []


def test_a_lone_label_joins_the_text_it_introduces_despite_a_low_score():
    embedder = _Embedder()
    sections = [
        _section(0, "text", "Tariff notes", ["Guide", "Harbour"]),
        _section(1, "text", "Run the installer before the crew arrives.", ["Guide", "Harbour"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert [chunk.content for chunk in chunks] == ["Tariff notes\n\nRun the installer before the crew arrives."]


def test_a_small_heading_does_not_join_a_cousin():
    embedder = _Embedder()
    sections = [
        _section(0, "text", "Run the installer.", ["Guide", "Setup", "Install"]),
        _section(1, "text", "Edit the file.", ["Guide", "Tuning", "Configure"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert [chunk.metadata.headings for chunk in chunks] == [
        ["Guide", "Setup", "Install"],
        ["Guide", "Tuning", "Configure"],
    ]
    assert embedder.batches == []


def test_a_parents_opening_text_joins_its_small_first_child():
    embedder = _Embedder()
    sections = [
        _section(0, "text", "These steps prepare the host.", ["Guide", "Setup"]),
        _section(1, "text", "Run the installer.", ["Guide", "Setup", "Install"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert [chunk.content for chunk in chunks] == ["These steps prepare the host.\n\nInstall\n\nRun the installer."]
    assert chunks[0].metadata.headings == ["Guide", "Setup"]


def test_a_parents_opening_text_waits_for_its_child_rather_than_joining_the_heading_before():
    embedder = _Embedder()
    sections = [
        _section(0, "text", "Measure the room.", ["Guide", "Survey"]),
        _section(1, "text", "These steps prepare the host.", ["Guide", "Setup"]),
        _section(2, "text", "Run the installer.", ["Guide", "Setup", "Install"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert [chunk.content for chunk in chunks] == [
        "Measure the room.",
        "These steps prepare the host.\n\nInstall\n\nRun the installer.",
    ]
    assert [chunk.metadata.headings for chunk in chunks] == [["Guide", "Survey"], ["Guide", "Setup"]]


def _subject_change(same: str, changed: str) -> str:
    """A paragraph over the maximum whose later sentences change subject."""
    same = same.strip()
    changed = changed.strip()
    count = 1
    text = same
    while count < 80:
        text = " ".join([same] * count + [changed] * 8)
        unchanged = " ".join([same] * count)
        # Leave room for the size check, which counts a blank line between sentences.
        if len(text) > BALANCED.max_chars and len(unchanged) <= BALANCED.max_chars - 80:
            return text
        count += 1
    return text


def test_a_long_paragraph_is_split_where_its_sentences_change_subject():
    same = "The crew walked the pier and wrote down the reading. "
    changed = "The tariff closed the quay and the crew went home. "
    paragraph = _subject_change(same, changed)
    embedder = _Embedder()
    section = _section(0, "text", paragraph, ["Guide", "North Pier"])

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
        _section(0, "text", _subject_change(same, changed), ["Guide", "North"]),
        _section(1, "text", _subject_change(south, changed), ["Guide", "South"]),
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
        _section(0, "text", _LAMP, ["Guide", "Setup"]),
        _section(1, "text", "Read the meter.", ["Guide", "Setup"]),
        _section(2, "text", "Open the gate.", ["Guide", "Route"]),
        _section(3, "text", _TARIFF, ["Guide", "Route"]),
    ]

    chunks = chunk_semantic(sections, filename="guide.txt", embedder=embedder)

    assert embedder.batches == [[_LAMP, "Read the meter.", "Open the gate.", _TARIFF]]
    assert [chunk.content for chunk in chunks] == [
        f"Setup\n\n{_LAMP}\n\nRead the meter.\n\nRoute\n\nOpen the gate.",
        _TARIFF,
    ]
    assert [chunk.metadata.headings for chunk in chunks] == [["Guide"], ["Guide", "Route"]]


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


def test_a_preamble_under_the_tiny_size_is_not_its_own_chunk():
    title = "Glentworth Parish Council IT Policy"
    assert len(title) < BALANCED.tiny_chars
    embedder = _Embedder()
    sections = [
        _section(0, "text", title, []),
        _section(1, "text", _LAMP, ["Access"]),
    ]

    chunks = chunk_semantic(sections, filename="policy.docx", embedder=embedder)

    assert len(chunks) == 1
    assert chunks[0].content.startswith(f"{title}\n\n")
    assert _LAMP in chunks[0].content
    assert chunks[0].metadata.headings == ["Access"]


def test_a_list_that_fits_the_maximum_stays_one_chunk():
    items = [f"{index} The panel records the complaint and the remedy sought." for index in range(1, 12)]
    data = "The committee considers the following:\n" + "\n".join(items)
    assert len(items) > 8
    assert len(data) <= BALANCED.max_chars
    embedder = _Embedder()

    chunks = chunk_semantic([_section(0, "list", data, ["Complaints"])], filename="complaints.docx", embedder=embedder)

    assert len(chunks) == 1
    assert chunks[0].content.count("The committee considers the following:") == 1
    assert "11 The panel records" in chunks[0].content


def test_a_long_list_lead_is_not_repeated_when_the_runs_merge():
    lead = ("The crew checks each item before leaving the yard. " * 6).strip()
    assert len(lead) > 200
    data = f"{lead}\n- Lamps\n- Meters"
    embedder = _Embedder()

    chunks = chunk_semantic([_section(0, "list", data, ["Guide"])], filename="kit.txt", embedder=embedder)

    assert len(chunks) == 1
    assert chunks[0].content.count(lead) == 1
    assert "- Lamps" in chunks[0].content


def test_one_oversized_passage_is_split_to_the_maximum():
    prose = ("word " * 600).strip()
    assert len(prose) > BALANCED.max_chars
    embedder = _Embedder()

    chunks = chunk_semantic([_section(0, "text", prose, ["Guide"])], filename="notes.txt", embedder=embedder)

    assert len(chunks) >= 2
    assert all(isinstance(chunk.content, str) and len(chunk.content) <= BALANCED.max_chars for chunk in chunks)


def test_numbered_clauses_keep_their_newlines_in_the_chunk():
    data = "6 During the investigation.\n7 While on suspension the employee stays home."
    embedder = _Embedder()

    chunks = chunk_semantic([_section(0, "text", data, ["Discipline"])], filename="policy.docx", embedder=embedder)

    assert chunks[0].content == data
