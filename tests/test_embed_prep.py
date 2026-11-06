from ragbytes.chunk.semantic.chunks import whole_after_first_pass
from ragbytes.chunk.semantic.embed_prep import HeadingPassages, PreparedSentence, prepare_sentences
from ragbytes.schemas import Section


def _section(
    index: int,
    kind: str,
    data: str,
    headings: list[str] | None = None,
    *,
    heading: str | None = None,
    subheading: str | None = None,
    page: int | None = None,
) -> Section:
    path = headings or []
    return Section(
        file_id="file-1",
        index=index,
        kind=kind,
        headings=path,
        heading=heading if heading is not None else (path[0] if path else None),
        subheading=subheading
        if subheading is not None
        else (path[-1] if len(path) > 1 else None),
        page=page,
        data=data,
    )


_FILLER = "The crew walked the pier and wrote down the reading."


def _with_room(tail: str) -> tuple[str, int]:
    """Build a paragraph long enough to be split, and say how many filler sentences lead it."""
    count = 0
    while len(" ".join([_FILLER] * count + [tail])) <= 1000:
        count += 1
    return " ".join([_FILLER] * count + [tail]), count


def _ordered(sections: list[Section]) -> list[PreparedSentence]:
    passages: list[PreparedSentence] = []
    for scope in prepare_sentences(sections):
        passages.extend(scope.to_embed)
        passages.extend(scope.whole)
    return sorted(passages, key=lambda item: item.order)


def _scope(sections: list[Section]) -> HeadingPassages:
    scopes = prepare_sentences(sections)
    assert len(scopes) == 1
    return scopes[0]


def test_a_small_paragraph_is_embedded_whole_under_its_heading():
    text = "Dr. Smith measured 3.14 lux. He logged it."
    section = _section(0, "text", text, ["Trial", "North Pier"], page=2)

    sentences = _ordered([section])

    assert [sentence.text for sentence in sentences] == [text]
    assert sentences[0].embed_text == f"Trial > North Pier\n\n{text}"
    assert sentences[0].heading == "Trial"
    assert sentences[0].subheading == "North Pier"
    assert sentences[0].headings == ["Trial", "North Pier"]
    assert sentences[0].page == 2
    assert sentences[0].section_index == 0
    assert sentences[0].section_id == section.id
    assert sentences[0].file_id == "file-1"
    assert sentences[0].kind == "text"


def test_a_paragraph_is_split_only_when_it_is_long_enough_to_change_subject():
    small = " ".join([_FILLER] * 8)
    long = " ".join([_FILLER] * 30)
    assert len(small) <= 1000
    assert len(long) > 1000

    short = _scope([_section(0, "text", small, ["Guide"])])
    long_passages = _scope([_section(1, "text", long, ["Guide"])])

    assert short.to_embed == []
    assert [unit.text for unit in short.whole] == [small]
    assert short.whole[0].embed_text == f"Guide\n\n{small}"
    assert short.whole[0].group is None
    assert long_passages.whole == []
    assert [unit.text for unit in long_passages.to_embed] == [_FILLER] * 30
    assert {unit.group for unit in long_passages.to_embed} == {0}
    assert {unit.heading for unit in long_passages.to_embed} == {"Guide"}


def test_a_long_paragraph_with_no_sentence_break_stays_one_chunk():
    text = ("word " * 400).strip()
    assert len(text) > 1000

    prepared = _scope([_section(0, "text", text, ["Guide"])])

    assert prepared.to_embed == []
    assert [unit.text for unit in prepared.whole] == [text]


def test_each_long_block_is_compared_on_its_own():
    long = " ".join([_FILLER] * 30)
    prepared = _scope([_section(0, "text", f"{long}\n\n{long}", ["Guide"])])

    assert prepared.whole == []
    groups = [unit.group for unit in prepared.to_embed]
    assert groups == [0] * 30 + [1] * 30
    assert [unit.order for unit in prepared.to_embed] == list(range(60))


def test_only_oversized_blocks_need_an_embedding_to_find_a_split():
    long = " ".join([_FILLER] * 30)
    sections = [
        _section(0, "text", "Warm the lamp. Read the meter.", ["Guide"]),
        _section(1, "text", long, ["Guide"]),
        _section(2, "list", "- One\n- Two", ["Guide"]),
        _section(3, "table", "| A |\n| --- |\n| 1 |", ["Guide"]),
        Section(index=4, kind="image", headings=["Guide"], heading="Guide", data="[Image: Wiring]"),
        Section(index=5, kind="chart", headings=["Guide"], heading="Guide", data="[Chart: Tide]"),
    ]

    prepared = _scope(sections)

    assert [unit.text for unit in prepared.whole] == [
        "Warm the lamp. Read the meter.",
        "- One\n- Two",
        "| A |\n| --- |\n| 1 |",
        "[Image: Wiring]",
        "[Chart: Tide]",
    ]
    assert {unit.group for unit in prepared.whole} == {None}
    assert [unit.text for unit in prepared.to_embed] == [_FILLER] * 30
    assert {unit.group for unit in prepared.to_embed} == {0}
    assert [unit.order for unit in prepared.whole] == [0, 31, 32, 33, 34]
    assert prepared.to_embed[0].order == 1
    assert prepared.to_embed[-1].order == 30


def test_each_heading_or_subheading_is_its_own_embedding_umbrella():
    long = " ".join([_FILLER] * 30)
    sections = [
        _section(0, "text", "Run the installer.", ["Guide", "Install"]),
        _section(1, "text", long, ["Guide", "Install"]),
        _section(2, "text", "Edit the file.", ["Guide", "Configure"]),
        _section(3, "list", "- One\n- Two", ["Guide", "Configure"]),
    ]

    scopes = prepare_sentences(sections)

    assert [(scope.heading, scope.subheading) for scope in scopes] == [
        ("Guide", "Install"),
        ("Guide", "Configure"),
    ]
    assert [scope.headings for scope in scopes] == [["Guide", "Install"], ["Guide", "Configure"]]
    assert [unit.text for unit in scopes[0].whole] == ["Run the installer."]
    assert [unit.text for unit in scopes[0].to_embed] == [_FILLER] * 30
    assert [unit.text for unit in scopes[1].whole] == ["Edit the file.", "- One\n- Two"]
    assert scopes[1].to_embed == []


def test_the_first_pass_puts_assembled_sections_back_into_whole_in_order():
    long = " ".join([_FILLER] * 30)
    sections = [
        _section(0, "text", "Before.", ["Guide", "Setup"]),
        _section(1, "text", long, ["Guide", "Setup"]),
        _section(2, "text", "After.", ["Guide", "Setup"]),
    ]
    scope = _scope(sections)

    passages = whole_after_first_pass(scope, {0: [10]})

    assert [passage.text for passage in passages] == [
        "Before.",
        " ".join([_FILLER] * 10),
        " ".join([_FILLER] * 20),
        "After.",
    ]
    assert [passage.order for passage in passages] == [0, 1, 11, 31]
    assert {passage.group for passage in passages} == {None}
    assert {passage.subheading for passage in passages} == {"Setup"}
    assert passages[1].embed_text == "Guide > Setup\n\n" + " ".join([_FILLER] * 10)


def test_a_long_block_with_no_cut_becomes_one_section_in_whole():
    long = " ".join([_FILLER] * 30)
    scope = _scope(
        [
            _section(0, "text", "Before.", ["Guide"]),
            _section(1, "text", long, ["Guide"]),
        ]
    )

    passages = whole_after_first_pass(scope)

    assert [passage.text for passage in passages] == ["Before.", long]


def test_list_runs_join_without_repeating_their_lead_in():
    items = [f"- Step {index:02d} checks the housing." for index in range(9)]
    data = "Bring the kit:\n" + "\n".join(items)
    scope = _scope([_section(0, "list", data, ["Guide", "Kit"])])

    kept_together = whole_after_first_pass(scope)
    cut = whole_after_first_pass(scope, {0: [1]})

    assert [passage.text for passage in kept_together] == [data]
    assert [passage.text for passage in cut] == [
        "Bring the kit:\n" + "\n".join(items[:5]),
        "Bring the kit:\n" + "\n".join(items[5:]),
    ]
    assert {passage.subheading for passage in cut} == {"Kit"}


def test_a_blank_line_starts_a_new_paragraph():
    section = _section(0, "text", "Warm the lamp. Read the meter.\n\nStore it dry.", ["Guide"])

    sentences = _ordered([section])

    assert [sentence.text for sentence in sentences] == ["Warm the lamp. Read the meter.", "Store it dry."]


def test_paragraphs_stay_in_file_order_when_the_heading_changes():
    sections = [
        _section(1, "text", "Edit the file.", ["Guide", "Configure"]),
        _section(0, "text", "Run the installer. Then restart.", ["Guide", "Install"]),
    ]

    sentences = _ordered(sections)

    assert [sentence.text for sentence in sentences] == [
        "Run the installer. Then restart.",
        "Edit the file.",
    ]
    assert [sentence.subheading for sentence in sentences] == ["Install", "Configure"]
    assert sentences[0].embed_text == "Guide > Install\n\nRun the installer. Then restart."
    assert sentences[1].embed_text == "Guide > Configure\n\nEdit the file."


def test_a_document_without_headings_embeds_the_paragraph_alone():
    section = _section(0, "text", "Warm the lamp. Read the meter.")

    sentences = _ordered([section])

    assert [sentence.embed_text for sentence in sentences] == ["Warm the lamp. Read the meter."]
    assert sentences[0].heading is None
    assert sentences[0].subheading is None
    assert sentences[0].headings == []


def test_abbreviations_initials_and_a_lower_case_continuation_stay_intact():
    tail = 'Ask Dr. Smith about the U.S. trial (see Fig. 2). He said "Go." Then wait... the lamp warms. e.g. this stays.'
    text, fillers = _with_room(tail)
    section = _section(0, "text", text, ["Guide"])

    sentences = _ordered([section])

    assert [sentence.text for sentence in sentences] == [_FILLER] * fillers + [
        "Ask Dr. Smith about the U.S. trial (see Fig. 2).",
        'He said "Go."',
        "Then wait... the lamp warms. e.g. this stays.",
    ]


def test_a_question_and_an_exclamation_each_end_a_sentence():
    text, fillers = _with_room("Is the seal seated? Yes! Replace it.")
    section = _section(0, "text", text, ["Guide"])

    sentences = _ordered([section])

    assert [sentence.text for sentence in sentences] == [_FILLER] * fillers + [
        "Is the seal seated?",
        "Yes!",
        "Replace it.",
    ]


def test_an_acronym_and_a_decimal_stay_whole_and_a_digit_can_start_a_sentence():
    tail = "Ph.D. students apply. Finished. 4 boats remain. The reading is 3.14 lux."
    text, fillers = _with_room(tail)
    section = _section(0, "text", text, ["Guide"])

    sentences = _ordered([section])

    assert [sentence.text for sentence in sentences] == [_FILLER] * fillers + [
        "Ph.D. students apply.",
        "Finished.",
        "4 boats remain.",
        "The reading is 3.14 lux.",
    ]


def test_a_line_without_a_stop_stays_one_sentence():
    section = _section(0, "text", "Minimum quantity", ["Guide"])

    sentences = _ordered([section])

    assert [sentence.text for sentence in sentences] == ["Minimum quantity"]
    assert sentences[0].embed_text == "Guide\n\nMinimum quantity"


def test_a_small_list_is_embedded_whole_under_its_heading():
    data = "- Check the seal. Replace it if it leaks.\n  - Tighten the bolt.\n1. Pack the bearings. Count them twice."
    section = _section(0, "list", data, ["Guide", "Setup"])

    sentences = _ordered([section])

    assert [sentence.text for sentence in sentences] == [data]
    assert sentences[0].embed_text == f"Guide > Setup\n\n{data}"
    assert sentences[0].kind == "list"
    assert sentences[0].heading == "Guide"
    assert sentences[0].subheading == "Setup"


def test_a_lead_in_stays_with_a_small_list():
    data = "Bring the kit:\n- Lamps\n- Meters"
    section = _section(0, "list", data, ["Guide", "Kit"])

    sentences = _ordered([section])

    assert [sentence.text for sentence in sentences] == [data]
    assert sentences[0].embed_text == f"Guide > Kit\n\n{data}"


def test_a_long_list_is_cut_between_items_into_even_runs():
    items = [f"- Step {index:02d} checks the housing." for index in range(9)]
    data = "Bring the kit:\n" + "\n".join(items)
    section = _section(0, "list", data, ["Guide"])

    prepared = _scope([section])

    assert prepared.whole == []
    assert [sentence.text for sentence in prepared.to_embed] == [
        "Bring the kit:\n" + "\n".join(items[:5]),
        "Bring the kit:\n" + "\n".join(items[5:]),
    ]
    assert {sentence.group for sentence in prepared.to_embed} == {0}
    assert {sentence.kind for sentence in prepared.to_embed} == {"list"}
    assert "checks the housing." in prepared.to_embed[0].text
    assert prepared.to_embed[0].text.count("\n- Step") == 5


def test_a_list_over_about_1000_characters_keeps_each_item_whole():
    first = "- " + ("Check the seal. " * 40).strip()
    second = "- " + ("Replace the seal. " * 40).strip()
    section = _section(0, "list", f"{first}\n{second}", ["Guide"])

    sentences = _ordered([section])

    assert [sentence.text for sentence in sentences] == [first, second]


def test_a_nested_entry_stays_with_its_parent_when_a_list_is_cut():
    lines = [f"- Step {index}." for index in range(4)]
    lines.extend(["- Step 4.", "  - Detail of step 4."])
    lines.extend(f"- Step {index}." for index in range(5, 9))
    section = _section(0, "list", "\n".join(lines), ["Guide"])

    sentences = _ordered([section])

    assert sentences[0].text.endswith("- Step 4.\n  - Detail of step 4.")
    assert sentences[1].text.startswith("- Step 5.")
    assert "Detail of step 4." not in sentences[1].text


def test_a_table_and_a_code_block_stay_whole_under_their_heading():
    sections = [
        _section(0, "table", "| Name | Value |\n| --- | --- |\n| Alpha | 1.5 |", ["Guide", "Readings"]),
        _section(1, "code", "def ready():\n    return 1.5\n", ["Guide", "Readings"]),
    ]

    sentences = _ordered(sections)

    assert [sentence.kind for sentence in sentences] == ["table", "code"]
    assert sentences[0].text == "| Name | Value |\n| --- | --- |\n| Alpha | 1.5 |"
    assert sentences[1].text == "def ready():\n    return 1.5"
    assert sentences[0].embed_text == "Guide > Readings\n\n| Name | Value |\n| --- | --- |\n| Alpha | 1.5 |"
    assert sentences[1].embed_text == "Guide > Readings\n\ndef ready():\n    return 1.5"
    assert sentences[1].heading == "Guide"
    assert sentences[1].subheading == "Readings"


def test_a_described_figure_stays_one_unit_and_a_bare_marker_is_left_out():
    picture = b"\x89PNG\r\n"
    described = Section(
        file_id="file-1",
        index=0,
        kind="image",
        headings=["Guide", "Setup"],
        heading="Guide",
        subheading="Setup",
        page=1,
        data="[Image: Wiring]",
        media=picture,
        media_type="image/png",
    )
    bare = Section(file_id="file-1", index=1, kind="image", headings=["Guide"], heading="Guide", data="[Image]")

    sentences = _ordered([bare, described])

    assert len(sentences) == 1
    assert sentences[0].text == "[Image: Wiring]"
    assert sentences[0].embed_text == "Guide > Setup\n\n[Image: Wiring]"
    assert sentences[0].kind == "image"
    assert sentences[0].page == 1


def test_a_short_label_before_a_figure_stays_with_that_figure():
    sections = [
        _section(0, "text", "Component Direction", ["Guide", "Setup"], page=1),
        Section(
            file_id="file-1",
            index=1,
            kind="image",
            headings=["Guide", "Setup"],
            heading="Guide",
            subheading="Setup",
            page=1,
            data="[Image: Wiring]",
        ),
    ]

    sentences = _ordered(sections)

    assert [sentence.text for sentence in sentences] == ["Component Direction\n[Image: Wiring]"]
    assert sentences[0].kind == "image"
    assert sentences[0].embed_text == "Guide > Setup\n\nComponent Direction\n[Image: Wiring]"
