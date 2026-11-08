from ragbytes.chunk.semantic_LLM.build_chunks import build_chunk_records
from ragbytes.chunk.semantic_LLM.text_prep import tag_sentences
from ragbytes.schemas import Section


def test_sentences_keep_the_section_they_came_from():
    sections = [
        Section(
            file_id="file-1",
            index=0,
            kind="text",
            title="Jane Smith",
            headings=["Experience", "Acme"],
            heading="Experience",
            subheading="Acme",
            page=1,
            data="Built the billing system. Led a team of four.",
        ),
        Section(
            file_id="file-1",
            index=1,
            kind="text",
            title="Jane Smith",
            headings=["Experience", "Northwind"],
            heading="Experience",
            subheading="Northwind",
            page=2,
            data="Migrated the ledger.",
        ),
    ]

    tagged = tag_sentences(sections)

    assert [sentence.text for sentence in tagged] == [
        "Built the billing system.",
        "Led a team of four.",
        "Migrated the ledger.",
    ]
    assert tagged[0].headings == ["Experience", "Acme"]
    assert tagged[0].page == 1
    assert tagged[2].subheading == "Northwind"
    assert tagged[2].page == 2
    assert tagged[0].title == "Jane Smith"


def test_one_heading_uses_the_shared_record_and_a_topic():
    sections = [
        Section(
            file_id="file-1",
            index=0,
            kind="text",
            title="Jane Smith",
            headings=["Experience", "Acme"],
            heading="Experience",
            subheading="Acme",
            page=1,
            data="Built the billing system.",
        )
    ]

    chunks = build_chunk_records(
        tag_sentences(sections),
        [(0, "Work history")],
        filename="cv.docx",
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.content == "Built the billing system."
    assert chunk.embed_text == "Jane Smith > Experience > Acme\n\nBuilt the billing system."
    metadata = chunk.metadata
    assert metadata.topic == "Work history"
    assert metadata.title == "Jane Smith"
    assert metadata.headings == ["Experience", "Acme"]
    assert metadata.heading == "Experience"
    assert metadata.subheading == "Acme"
    assert metadata.heading_paths == [["Experience", "Acme"]]
    assert metadata.page == 1
    assert metadata.pages == [1]
    assert metadata.format == "text"
    assert metadata.filename == "cv.docx"
    assert metadata.chunk_number == 0


def test_a_slice_across_headings_lists_each_path_and_page():
    sections = [
        Section(
            file_id="file-1",
            index=0,
            kind="text",
            title="Jane Smith",
            headings=["Experience", "Acme"],
            heading="Experience",
            subheading="Acme",
            page=1,
            data="Built the billing system. Led a team of four.",
        ),
        Section(
            file_id="file-1",
            index=1,
            kind="text",
            title="Jane Smith",
            headings=["Experience", "Northwind"],
            heading="Experience",
            subheading="Northwind",
            page=2,
            data="Migrated the ledger.",
        ),
    ]

    chunks = build_chunk_records(
        tag_sentences(sections),
        [(0, "Work history")],
        filename="cv.docx",
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.content == "Built the billing system. Led a team of four. Migrated the ledger."
    assert "Work history" not in chunk.content
    assert chunk.embed_text == (
        "Jane Smith\n\n"
        "Experience > Acme\n\n"
        "Built the billing system. Led a team of four.\n\n"
        "Experience > Northwind\n\n"
        "Migrated the ledger."
    )
    metadata = chunk.metadata
    assert metadata.topic == "Work history"
    assert metadata.heading == "Experience"
    assert metadata.subheading == "Acme"
    assert metadata.headings == ["Experience", "Acme"]
    assert metadata.heading_paths == [["Experience", "Acme"], ["Experience", "Northwind"]]
    assert metadata.page == 1
    assert metadata.pages == [1, 2]
    assert (metadata.details.start, metadata.details.end) == (0, len(chunk.content))


def test_a_blank_topic_is_null():
    sections = [
        Section(file_id="file-1", index=0, kind="text", data="One sentence here."),
    ]

    chunks = build_chunk_records(tag_sentences(sections), [(0, "  ")], filename="notes.txt")

    assert chunks[0].metadata.topic is None
    assert chunks[0].metadata.heading_paths == []
    assert chunks[0].metadata.pages == []
