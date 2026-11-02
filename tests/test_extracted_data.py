from shark_byte.extract.complex import prepare_for_chunking, read_complex
from shark_byte.extract.extracted_data import ExtractedData
from shark_byte.schemas import Section


def test_extracted_data_keeps_simple_and_complex_sections():
    text = Section(index=0, kind="text", data="Install the package.")
    picture = Section(index=1, kind="image", data="[Image]")
    mixed = Section(index=2, kind="complex", data="[Complex]")
    table = Section(index=3, kind="table", data="| A |\n| --- |")

    extracted = ExtractedData([text, picture, mixed, table])

    assert extracted.all_sections == [text, picture, mixed, table]
    assert extracted.simple_sections == [text, picture, table]
    assert extracted.complex_sections == [mixed]


def test_complex_pass_keeps_a_leftover_and_leaves_readable_sections():
    text = Section(index=0, kind="text", data="Before.")
    mixed = Section(index=1, kind="complex", data="[Complex]", media=b"<td>Logo</td>")
    table = Section(index=2, kind="table", data="| A |\n| --- |")

    assert read_complex(mixed) == [mixed]
    assert prepare_for_chunking([text, mixed, table]) == [text, mixed, table]
