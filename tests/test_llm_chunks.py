from ragbytes.chunk.semantic_LLM.build_chunks import (
    assemble_llm_chunks,
    bound_splits,
    build_chunk_records,
)
from ragbytes.chunk.semantic_LLM.openAI_call import (
    _number_window,
    ask_for_figure_title,
    read_figure_title,
)
from ragbytes.chunk.semantic_LLM.text_prep import (
    FigureUnit,
    ProseRun,
    absorb_captions,
    figure_message,
    numbered_lines,
    segment_sections,
    tag_sentences,
)
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


def test_a_table_between_prose_is_its_own_chunk():
    table = "| Year | Amount |\n| --- | --- |\n| 2024 | 10 |"
    sections = [
        Section(
            file_id="file-1",
            index=0,
            kind="text",
            title="Report",
            headings=["Results"],
            heading="Results",
            page=1,
            data="Built the billing system.",
        ),
        Section(
            file_id="file-1",
            index=1,
            kind="table",
            title="Report",
            headings=["Results"],
            heading="Results",
            page=1,
            data=table,
        ),
        Section(
            file_id="file-1",
            index=2,
            kind="text",
            title="Report",
            headings=["Results"],
            heading="Results",
            page=2,
            data="Migrated the ledger.",
        ),
    ]

    units = segment_sections(sections)
    chunks = assemble_llm_chunks(
        units,
        [[(0, "Work history")], [(0, "Next role")]],
        ["Yearly takings"],
        filename="report.docx",
    )

    assert [type(unit) for unit in units] == [ProseRun, FigureUnit, ProseRun]
    assert len(chunks) == 3
    assert chunks[0].content == "Built the billing system."
    assert chunks[1].content == table
    assert chunks[2].content == "Migrated the ledger."
    assert table not in chunks[0].content
    assert table not in chunks[2].content
    assert "Yearly takings" not in chunks[1].content
    assert chunks[0].metadata.topic == "Work history"
    assert chunks[1].metadata.topic == "Yearly takings"
    assert chunks[2].metadata.topic == "Next role"
    assert chunks[1].metadata.format == "table"
    assert "Yearly takings" not in chunks[1].embed_text
    assert [chunk.metadata.chunk_number for chunk in chunks] == [0, 1, 2]
    assert chunks[1].metadata.details.start == chunks[0].metadata.details.end + 2
    assert chunks[2].metadata.details.start == chunks[1].metadata.details.end + 2
    assert chunks[1].metadata.details.end - chunks[1].metadata.details.start == len(table)


def test_an_image_between_prose_is_its_own_chunk():
    png = b"\x89PNG\r\n\x1a\nfake"
    label = "[Image: sales chart]"
    sections = [
        Section(file_id="file-1", index=0, kind="text", page=1, data="Alpha sentence."),
        Section(
            file_id="file-1",
            index=1,
            kind="image",
            title="Report",
            headings=["Results"],
            heading="Results",
            page=2,
            data=label,
            media=png,
            media_type="image/png",
        ),
        Section(file_id="file-1", index=2, kind="text", page=2, data="Beta sentence."),
    ]

    chunks = assemble_llm_chunks(
        segment_sections(sections),
        [[(0, "Opening")], [(0, "Closing")]],
        ["Quarterly revenue"],
        filename="report.pdf",
    )

    assert len(chunks) == 3
    assert chunks[0].content == "Alpha sentence."
    assert chunks[2].content == "Beta sentence."
    assert label not in chunks[0].content
    assert label not in chunks[2].content
    image = chunks[1]
    assert image.content == png
    assert image.metadata.format == "image"
    assert image.metadata.topic == "Quarterly revenue"
    assert image.metadata.media_type == "image/png"
    assert image.metadata.page == 2
    assert image.metadata.pages == [2]
    assert image.metadata.heading_paths == [["Results"]]
    assert "Quarterly revenue" not in image.embed_text
    assert image.embed_text == f"Report > Results\n\n{label}"
    assert image.metadata.details.start == chunks[0].metadata.details.end + 2
    assert image.metadata.details.end - image.metadata.details.start == len(label)
    assert chunks[2].metadata.details.start == image.metadata.details.end + 2


def test_a_bare_figure_is_left_out_of_the_prose():
    sections = [
        Section(file_id="file-1", index=0, kind="text", data="Alpha sentence."),
        Section(file_id="file-1", index=1, kind="image", data="[Image]"),
        Section(file_id="file-1", index=2, kind="chart", data="[Chart]"),
        Section(file_id="file-1", index=3, kind="complex", data="[Complex]"),
        Section(file_id="file-1", index=4, kind="text", data="Beta sentence."),
    ]

    units = segment_sections(sections)

    assert len(units) == 1
    assert isinstance(units[0], ProseRun)
    assert [sentence.text for sentence in units[0].sentences] == [
        "Alpha sentence.",
        "Beta sentence.",
    ]

    kept = segment_sections(
        [
            Section(
                file_id="file-1",
                index=0,
                kind="image",
                data="[Image]",
                media=b"png",
                media_type="image/png",
            )
        ]
    )
    assert len(kept) == 1
    assert isinstance(kept[0], FigureUnit)


def test_a_figure_message_sends_the_picture_or_the_table():
    png = b"\x89PNG\r\n\x1a\nfake"
    image = Section(
        file_id="file-1",
        index=0,
        kind="image",
        title="Report",
        headings=["Results"],
        heading="Results",
        page=2,
        data="[Image: sales chart]",
        media=png,
        media_type="image/jpg",
    )
    table = "| Year | Amount |\n| --- | --- |\n| 2024 | 10 |"
    grid = Section(
        file_id="file-1",
        index=1,
        kind="table",
        title="Report",
        headings=["Results"],
        heading="Results",
        page=3,
        data=table,
    )
    caption = Section(file_id="file-1", index=2, kind="image", data="[Image: org chart]")

    text, media, media_type = figure_message(image)
    assert media == png
    assert media_type == "image/jpeg"
    assert text == "[Image: sales chart]\nReport > Results\nPage 2"

    text, media, media_type = figure_message(grid)
    assert (text, media, media_type) == (table, None, None)

    text, media, media_type = figure_message(caption)
    assert (text, media, media_type) == ("[Image: org chart]", None, None)
    assert len(segment_sections([caption])) == 1

    chart = Section(
        file_id="file-1",
        index=3,
        kind="chart",
        headings=["Results"],
        heading="Results",
        data="[Chart: Revenue]\n" + table,
    )
    text, media, media_type = figure_message(chart)
    assert media is None
    assert text == "[Chart: Revenue]\n" + table
    assert "Results" not in text
    chart_units = segment_sections(
        [
            Section(file_id="file-1", index=0, kind="text", data="Before the chart."),
            chart,
            Section(file_id="file-1", index=4, kind="text", data="After the chart."),
        ]
    )
    assert [type(unit) for unit in chart_units] == [ProseRun, FigureUnit, ProseRun]


def test_a_list_is_one_block_and_keeps_its_lines():
    data = (
        "The shop opens at seven. Bring the kit:\n"
        "- Check the seal. Replace it if it leaks.\n"
        "  and wipe the rim\n"
        "  - Tighten the bolt.\n"
        "1. Pack the bearings. Count them twice.\n"
        "- Lock the till\n"
        "- Count the float"
    )
    sections = [
        Section(
            file_id="file-1",
            index=0,
            kind="list",
            title="Guide",
            headings=["Setup"],
            heading="Setup",
            page=3,
            data=data,
        )
    ]

    tagged = tag_sentences(sections)
    block = (
        "Bring the kit:\n"
        "- Check the seal. Replace it if it leaks.\n"
        "  and wipe the rim\n"
        "  - Tighten the bolt.\n"
        "1. Pack the bearings. Count them twice.\n"
        "- Lock the till\n"
        "- Count the float"
    )

    assert [sentence.text for sentence in tagged] == [
        "The shop opens at seven.",
        block,
    ]
    assert {sentence.kind for sentence in tagged} == {"list"}
    assert _number_window([sentence.text for sentence in tagged]) == (
        "[0] The shop opens at seven.\n"
        "[1] Bring the kit:\n"
        "- Check the seal. Replace it if it leaks.\n"
        "  and wipe the rim\n"
        "  - Tighten the bolt.\n"
        "1. Pack the bearings. Count them twice.\n"
        "- Lock the till\n"
        "- Count the float"
    )

    chunks = build_chunk_records(tagged, [(0, "Opening"), (1, "Kit")], filename="guide.docx")

    assert [chunk.content for chunk in chunks] == [
        "The shop opens at seven.",
        block,
    ]
    assert chunks[1].metadata.format == "list"
    assert chunks[0].metadata.topic == "Opening"
    assert chunks[1].metadata.topic == "Kit"
    assert chunks[1].embed_text == f"Guide > Setup\n\n{block}"
    assert chunks[1].metadata.details.start == len(chunks[0].content) + 2
    assert chunks[1].metadata.details.end - chunks[1].metadata.details.start == len(block)


def test_prose_around_a_list_keeps_sentences_and_the_list_lines():
    sections = [
        Section(
            file_id="file-1",
            index=0,
            kind="text",
            headings=["Closing"],
            heading="Closing",
            page=1,
            data="The shop opens at seven. The lights stay on.",
        ),
        Section(
            file_id="file-1",
            index=1,
            kind="list",
            headings=["Closing"],
            heading="Closing",
            page=1,
            data="- Flour\n- Water",
        ),
        Section(
            file_id="file-1",
            index=2,
            kind="text",
            headings=["Closing"],
            heading="Closing",
            page=1,
            data="The office dog is named Biscuit.",
        ),
    ]

    tagged = tag_sentences(sections)
    chunks = build_chunk_records(tagged, [(0, "Shop")], filename="notes.txt")

    assert [sentence.text for sentence in tagged] == [
        "The shop opens at seven.",
        "The lights stay on.",
        "- Flour\n- Water",
        "The office dog is named Biscuit.",
    ]
    assert len(segment_sections(sections)) == 1
    assert chunks[0].content == (
        "The shop opens at seven. The lights stay on.\n"
        "- Flour\n"
        "- Water\n\n"
        "The office dog is named Biscuit."
    )
    assert chunks[0].metadata.format == "text"
    assert chunks[0].embed_text == f"Closing\n\n{chunks[0].content}"


def test_a_list_with_no_markers_is_read_as_prose():
    sections = [
        Section(
            file_id="file-1",
            index=0,
            kind="list",
            data="The shop opens at seven. The lights stay on.",
        )
    ]

    chunks = build_chunk_records(
        tag_sentences(sections),
        [(0, "Opening")],
        filename="notes.txt",
    )

    assert chunks[0].content == "The shop opens at seven. The lights stay on."
    assert chunks[0].metadata.format == "list"


def test_a_short_label_stays_on_its_list_and_code_keeps_its_lines():
    listed = tag_sentences(
        [Section(file_id="file-1", index=0, kind="list", data="Ordered\n1. foo\n2. bar")]
    )
    code = tag_sentences(
        [
            Section(
                file_id="file-1",
                index=0,
                kind="code",
                data="// Some comments\nline 1 of code\nline 2 of code",
            )
        ]
    )
    bullets = tag_sentences(
        [
            Section(
                file_id="file-1",
                index=0,
                kind="text",
                data=(
                    "This guideline does not cover:\n"
                    "- recall intervals for scale and polish\n"
                    "- the prescription of dental radiographs\n\n"
                    "The following guidance is based on the evidence."
                ),
            )
        ]
    )

    assert [sentence.text for sentence in listed] == ["Ordered\n1. foo\n2. bar"]
    assert [sentence.text for sentence in code] == [
        "// Some comments\nline 1 of code\nline 2 of code"
    ]
    assert [sentence.text for sentence in bullets] == [
        (
            "This guideline does not cover:\n"
            "- recall intervals for scale and polish\n"
            "- the prescription of dental radiographs"
        ),
        "The following guidance is based on the evidence.",
    ]


def test_a_heading_change_starts_a_chunk_and_a_fragment_joins_its_heading():
    till = (
        "The card machine settles overnight. "
        "Count the float to fifty pounds before the first customer, "
        "and put the notes in the blue tin under the counter."
    )
    closing = (
        "Close the shop before you go home. "
        "Turn both ovens off, wipe the steel counters, and lock the shop door."
    )
    sections = [
        Section(
            file_id="file-1",
            index=0,
            kind="text",
            headings=["The till"],
            heading="The till",
            data=till,
        ),
        Section(
            file_id="file-1",
            index=1,
            kind="text",
            headings=["Before you leave"],
            heading="Before you leave",
            data=closing,
        ),
        Section(
            file_id="file-1",
            index=2,
            kind="text",
            headings=["Before you leave"],
            heading="Before you leave",
            data="!!!!!!",
        ),
        Section(
            file_id="file-1",
            index=3,
            kind="text",
            headings=["Before you leave"],
            heading="Before you leave",
            data="This is bold text.",
        ),
    ]
    tagged = tag_sentences(sections)
    bang = next(index for index, sentence in enumerate(tagged) if sentence.text == "!!!!!!")
    bold = next(index for index, sentence in enumerate(tagged) if sentence.text == "This is bold text.")

    splits = bound_splits(tagged, [(0, "Everything"), (bang, "Marks"), (bold, "Bold")])
    chunks = build_chunk_records(tagged, splits, filename="notes.docx")

    assert [chunk.metadata.heading for chunk in chunks] == ["The till", "Before you leave"]
    assert chunks[1].metadata.topic == "Before you leave"
    assert "lock the shop door" in chunks[0].content or "blue tin" in chunks[0].content
    assert "!!!!!!" in chunks[1].content
    assert "This is bold text." in chunks[1].content
    assert "blue tin" not in chunks[1].content


def test_a_caption_is_written_onto_the_figure_it_introduces():
    sections = [
        Section(file_id="file-1", index=0, kind="text", data="Count the float before you leave."),
        Section(
            file_id="file-1",
            index=1,
            kind="text",
            data="And now, go to http://127.0.0.1:8000/redoc.",
        ),
        Section(file_id="file-1", index=2, kind="image", data="[Image: ReDoc]"),
        Section(file_id="file-1", index=3, kind="text", data="Right aligned columns"),
        Section(
            file_id="file-1",
            index=4,
            kind="table",
            data="| Option | Description |\n| --- | --- |\n| data | path |",
        ),
    ]

    units = absorb_captions(segment_sections(sections))

    assert [type(unit) for unit in units] == [ProseRun, FigureUnit, FigureUnit]
    assert units[0].sentences[0].text == "Count the float before you leave."
    assert units[1].section.data.startswith("And now, go to http://127.0.0.1:8000/redoc.")
    assert "[Image: ReDoc]" in units[1].section.data
    assert units[2].section.data.startswith("Right aligned columns")
    assert numbered_lines(
        ["Count the float before you leave."],
        headings=[["The till"]],
    ) == "# The till\n[0] Count the float before you leave."


def test_a_figure_title_is_read_from_the_reply():
    assert read_figure_title('{"title": "  Quarterly revenue  "}') == "Quarterly revenue"
    assert read_figure_title('{"title": "  "}') == ""
    assert read_figure_title(None, refusal="no") == ""
    assert read_figure_title("not json") == ""
    assert read_figure_title('{"title": 3}') == ""
    assert ask_for_figure_title("  ") == ""
