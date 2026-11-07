import base64
import io

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_BREAK
from docx.opc.constants import CONTENT_TYPE, RELATIONSHIP_TYPE
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt
from PIL import Image as PilImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ragbytes.extract.extractors import (
    extract_docx,
    extract_html,
    extract_markdown,
    extract_pdf,
    extract_text,
)


def test_plain_text_normalizes_headings_and_paragraphs():
    raw = (
        "Guide\n"
        "=====\n"
        "\n"
        "Install the package.\n"
        "It is small.\n"
        "\n"
        "Setup\n"
        "-----\n"
        "\n"
        "- Use pip\n"
        "- Then run it\n"
    )

    sections = extract_text(raw.encode())

    assert _view(sections) == [
        ("text", None, None, None, "Install the package. It is small."),
        ("list", "Setup", None, None, "- Use pip\n- Then run it"),
    ]
    assert {section.title for section in sections} == {"Guide"}
    assert _ids_are_unique(sections)


def test_markdown_normalizes_structure_images_and_tables():
    raw = (
        "#### Deep\n"
        "\n"
        "See the ![Plot](plot.png) and the [guide](https://example.com).\n"
        "\n"
        "| Quarter | Revenue |\n"
        "| --- | --- |\n"
        "| Q1 | 10 |\n"
        "\n"
        "```\n"
        "keep this\n"
        "```\n"
    )

    sections = extract_markdown(raw.encode())

    assert _view(sections) == [
        ("text", "Deep", None, None, "See the [Image: Plot] and the guide."),
        ("image", "Deep", None, None, "[Image: Plot]"),
        (
            "table",
            "Deep",
            None,
            None,
            "| Quarter | Revenue |\n| --- | --- |\n| Q1 | 10 |",
        ),
        ("code", "Deep", None, None, "keep this"),
    ]
    assert [section.headings for section in sections] == [["Deep"]] * len(sections)
    image = sections[1]
    assert image.media is None
    assert _ids_are_unique(sections)


def test_html_extracts_headings_table_image_and_chart():
    raw = """
    <html><body>
      <h1>Report</h1>
      <p>Intro text.</p>
      <h2>Numbers</h2>
      <ul>
        <li>First</li>
        <li>Second</li>
      </ul>
      <table>
        <tr><th>Quarter</th><th>Revenue</th></tr>
        <tr><td>Q1</td><td>10</td></tr>
      </table>
      <figure>
        <img alt="Ignored alt">
        <figcaption>Front office</figcaption>
      </figure>
      <figure>
        <svg class="chart" aria-label="Revenue chart"></svg>
      </figure>
      <img width="12" height="12" alt="icon">
    </body></html>
    """

    sections = extract_html(raw.encode())

    assert _view(sections) == [
        ("text", None, None, None, "Intro text."),
        ("list", "Numbers", None, None, "- First\n- Second"),
        (
            "table",
            "Numbers",
            None,
            None,
            "| Quarter | Revenue |\n| --- | --- |\n| Q1 | 10 |",
        ),
        ("image", "Numbers", None, None, "[Image: Front office]"),
        ("chart", "Numbers", None, None, "[Chart: Revenue chart]"),
    ]
    assert {section.title for section in sections} == {"Report"}
    assert sections[3].media is None
    assert _ids_are_unique(sections)


def test_docx_extracts_headings_list_table_and_image():
    document = Document()
    document.add_paragraph("Guide", style="Heading 1")
    document.add_paragraph("Install the package.")
    document.add_paragraph("Setup", style="Heading 2")
    document.add_paragraph("Use pip.", style="List Bullet")
    document.add_paragraph("Then run it.", style="List Bullet")
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Quarter"
    table.rows[0].cells[1].text = "Revenue"
    table.rows[1].cells[0].text = "Q1"
    table.rows[1].cells[1].text = "10"

    picture = io.BytesIO()
    PilImage.new("RGB", (80, 60), "red").save(picture, format="PNG")
    picture_bytes = picture.getvalue()
    picture.seek(0)
    document.add_picture(picture, width=Inches(1))
    doc_pr = document.paragraphs[-1]._element.find(".//" + qn("wp:docPr"))
    doc_pr.set("descr", "Front office")

    sections = extract_docx(_docx_bytes(document))

    assert _view(sections) == [
        ("text", None, None, None, "Install the package."),
        ("list", "Setup", None, None, "- Use pip.\n- Then run it."),
        (
            "table",
            "Setup",
            None,
            None,
            "| Quarter | Revenue |\n| --- | --- |\n| Q1 | 10 |",
        ),
        ("image", "Setup", None, None, "[Image: Front office]"),
    ]
    assert {section.title for section in sections} == {"Guide"}
    image = sections[-1]
    assert image.media == picture_bytes
    assert image.media_type == "image/png"
    assert _ids_are_unique(sections)


def test_docx_treats_bold_larger_text_as_headings():
    document = Document()
    title = document.add_paragraph()
    title_run = title.add_run("Guide")
    title_run.bold = True
    title_run.font.size = Pt(16)
    document.add_paragraph("Install the package.")
    section = document.add_paragraph()
    section_run = section.add_run("Setup")
    section_run.bold = True
    section_run.font.size = Pt(13)
    body = document.add_paragraph()
    body_run = body.add_run("Then run it.")
    body_run.font.size = Pt(11)
    note = document.add_paragraph()
    note_run = note.add_run("This reminder stays in the paragraph.")
    note_run.bold = True
    note_run.font.size = Pt(11)

    sections = extract_docx(_docx_bytes(document))

    assert [(section.title, section.headings, section.data) for section in sections] == [
        ("Guide", [], "Install the package."),
        ("Guide", ["Setup"], "Then run it."),
        ("Guide", ["Setup"], "This reminder stays in the paragraph."),
    ]


def test_docx_keeps_each_bullet_on_one_line():
    document = Document()
    first = document.add_paragraph(style="List Bullet")
    first.add_run("alpha line")
    first.add_run().add_break(WD_BREAK.LINE)
    first.add_run("continues")
    document.add_paragraph("beta", style="List Bullet")

    sections = extract_docx(_docx_bytes(document))

    assert [section.data.splitlines() for section in sections] == [
        ["- alpha line continues", "- beta"],
    ]


def test_docx_extracts_chart_values():
    document = Document()
    document.add_paragraph("Results", style="Heading 1")
    _add_chart(document)

    sections = extract_docx(_docx_bytes(document))

    assert _view(sections) == [
        (
            "chart",
            "Results",
            None,
            None,
            "[Chart: Revenue]\n"
            "| Category | Sales | Costs |\n"
            "| --- | --- | --- |\n"
            "| Jan | 10 | 4 |\n"
            "| Feb | 12 | 5 |",
        )
    ]
    assert _ids_are_unique(sections)


def test_pdf_keeps_a_wrapped_paragraph_together():
    sections = extract_pdf(_wrapped_pdf_bytes())

    assert _view(sections) == [
        (
            "text",
            None,
            None,
            1,
            "The extractor should keep this marked sentence together even when "
            "the PDF wraps it across several visual lines on the page. A second "
            "sentence stays in the same paragraph until a real paragraph break.",
        ),
        (
            "text",
            None,
            None,
            1,
            "Next paragraph starts after a normal gap and should stay separate.",
        ),
    ]


def test_pdf_extracts_headings_table_and_image():
    sections = extract_pdf(_pdf_bytes())

    assert _view(sections) == [
        ("text", None, None, 1, "First paragraph of the introduction."),
        ("text", None, None, 1, "Second paragraph stays separate."),
        ("text", "Revenue", None, 1, "Figures for the year follow."),
        (
            "table",
            "Revenue",
            None,
            1,
            "| Quarter | Revenue |\n| --- | --- |\n| Q1 | 10 |\n| Q2 | 12 |",
        ),
        ("image", "Revenue", None, 1, "[Image: The photo shows the office.]"),
    ]
    assert {section.title for section in sections} == {"Annual Report"}
    image = next(section for section in sections if section.kind == "image")
    assert image.media is not None
    assert image.media.startswith(b"\x89PNG")
    assert image.media_type == "image/png"
    assert sum(section.data.count("Q1") for section in sections) == 1
    assert _ids_are_unique(sections)


def test_markdown_keeps_images_in_headings_and_wrapped_items():
    raw = "\n".join(
        [
            "## Title ![Plot](plot.png)",
            "",
            "- See the",
            "  ![Plot](plot.png) now",
            "",
            "[id]: https://example.com",
            "",
            "Paragraph.",
            "",
        ]
    )

    sections = extract_markdown(raw.encode())

    assert _view(sections) == [
        ("image", "Title", None, None, "[Image: Plot]"),
        ("list", "Title", None, None, "- See the [Image: Plot] now"),
        ("image", "Title", None, None, "[Image: Plot]"),
        ("text", "Title", None, None, "Paragraph."),
    ]


def test_markdown_keeps_a_lead_in_with_nested_and_wrapped_items():
    raw = "Bring:\n\n- Use pip\n  to install\n  - Then test\n- Run it\n\nDone.\n"

    sections = extract_markdown(raw.encode())

    assert _view(sections) == [
        ("list", None, None, None, "Bring:\n- Use pip to install\n  - Then test\n- Run it"),
        ("text", None, None, None, "Done."),
    ]


def test_html_keeps_list_structure_and_skips_navigation():
    raw = """
    <html><body>
      <nav>Home</nav>
      <div role="navigation">Menu</div>
      <div hidden>Secret</div>
      <h1>Report</h1>
      <p>Bring:</p>
      <ul>
        <li>First<ul><li>Nested</li></ul></li>
        <li>Second<table><tr><td>A</td><td>B</td></tr></table></li>
      </ul>
    </body></html>
    """

    sections = extract_html(raw.encode())

    assert _view(sections) == [
        ("list", "Report", None, None, "Bring:\n- First\n  - Nested\n- Second"),
        ("table", "Report", None, None, "| A | B |\n| --- | --- |"),
    ]


def test_html_reads_only_the_main_region_and_skips_page_chrome():
    languages = "".join(
        f'<li><a href="https://{code}.example.org/Linux" hreflang="{code}">{code}</a></li>'
        for code in ("de", "fr", "es", "it", "nl", "pl")
    )
    raw = f"""
    <html><body>
      <a href="#content">Jump to content</a>
      <header><img src="logo.png" alt="Site logo"><div role="search">Search</div></header>
      <main id="content">
        <header><h1>Linux</h1><ul>{languages}</ul></header>
        <p>Linux is a family of operating systems.</p>
        <blockquote><p>Free as in freedom.</p><footer>Richard Stallman</footer></blockquote>
        <footer>Categories: Linux</footer>
      </main>
      <footer>This page was last edited today.</footer>
    </body></html>
    """

    sections = extract_html(raw.encode())

    assert _view(sections) == [
        ("text", "Linux", None, None, "Linux is a family of operating systems."),
        ("text", "Linux", None, None, "Free as in freedom."),
        ("text", "Linux", None, None, "Richard Stallman"),
    ]


def test_html_keeps_a_title_set_just_outside_the_main_region():
    raw = """
    <html><body>
      <header><h1>Release notes</h1></header>
      <main><h2>Fixes</h2><p>The crash on start is fixed.</p></main>
    </body></html>
    """

    sections = extract_html(raw.encode())

    assert _view(sections) == [
        ("text", "Fixes", None, None, "The crash on start is fixed."),
    ]
    assert sections[0].title == "Release notes"


def test_docx_keeps_lead_in_nested_items_and_merged_cells():
    document = Document()
    document.add_paragraph("Guide", style="Heading 1")
    document.add_paragraph("Bring:")
    document.add_paragraph("Use pip.", style="List Bullet")
    document.add_paragraph("the package.", style="List Continue")
    child = document.add_paragraph("Then test.", style="List Bullet")
    _set_list_level(child, 1)
    outlined = document.add_paragraph("Details")
    outlined._element.get_or_add_pPr().append(
        parse_xml(f'<w:outlineLvl {nsdecls("w")} w:val="1"/>')
    )
    document.add_paragraph("The body follows the outline heading.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).merge(table.cell(1, 0))
    table.cell(0, 0).text = "Year"
    table.cell(0, 1).text = "Q1"
    table.cell(1, 1).text = "Q2"

    sections = extract_docx(_docx_bytes(document))

    assert _view(sections) == [
        (
            "list",
            None,
            None,
            None,
            "Bring:\n- Use pip. the package.\n  - Then test.",
        ),
        ("text", "Details", None, None, "The body follows the outline heading."),
        (
            "table",
            "Details",
            None,
            None,
            "| Year | Q1 |\n| --- | --- |\n|  | Q2 |",
        ),
    ]
    assert {section.title for section in sections} == {"Guide"}
    assert next(section for section in sections if section.kind == "table").data.count("Year") == 1


def test_pdf_groups_bullets_and_drops_repeated_margin_text():
    sections = extract_pdf(_listed_pdf_bytes())

    assert _view(sections) == [
        ("list", None, None, 1, "Bring:\n- Use pip\n- Then run it"),
        ("text", None, None, 1, "continued from above stays in the paragraph."),
    ]

    paged = extract_pdf(_footer_pdf_bytes())

    assert [section.page for section in paged] == [1, 2, 3]
    assert all("confidential" not in section.data.lower() for section in paged)
    assert all(section.subheading is None for section in paged)


def test_pdf_drops_a_footer_whose_page_number_wraps_and_contents_lines():
    sections = extract_pdf(_contents_and_shifting_footer_pdf_bytes())

    assert [section.data for section in sections] == [
        "Overview text for page 2.",
        "Overview text for page 3.",
        "Overview text for page 4.",
    ]


def test_pdf_keeps_body_text_and_nests_bullets():
    kept = extract_pdf(_body_marker_pdf_bytes())

    assert any(section.data == "12" and section.heading is None for section in kept)
    assert all(section.data != "4" for section in kept)
    assert any(
        "Bring the package" in section.data and section.heading is None for section in kept
    )

    nested = extract_pdf(_nested_bullet_pdf_bytes())

    assert [section.data for section in nested if section.kind == "list"] == [
        "- Use pip\n  - Then test\n- Run it"
    ]


def test_pdf_reads_a_narrow_gap_as_two_columns():
    sections = extract_pdf(_tight_column_pdf_bytes())
    text = "\n".join(section.data for section in sections)
    left = text.find("left column explains the installation")
    right = text.find("right column explains how to run")

    assert left != -1 and right != -1 and left < right
    assert not any(
        "left column explains" in section.data and "right column explains" in section.data
        for section in sections
    )


def test_pdf_reads_each_column_before_the_next():
    sections = extract_pdf(_two_column_pdf_bytes())
    text = "\n".join(section.data for section in sections)
    left = text.find("left column explains the installation")
    right = text.find("right column explains how to run")

    assert left != -1 and right != -1 and left < right
    assert not any(
        "left column explains" in section.data and "right column explains" in section.data
        for section in sections
    )


def test_pdf_leaves_text_on_an_image_out_of_the_text():
    sections = extract_pdf(_figure_pdf_bytes())

    assert any(section.kind == "image" for section in sections)
    assert any("caption sits below the figure" in section.data for section in sections)
    assert all("Hidden axis label" not in section.data for section in sections)


def test_markdown_data_uri_keeps_image_bytes():
    picture = io.BytesIO()
    PilImage.new("RGB", (40, 30), "blue").save(picture, format="PNG")
    payload = base64.b64encode(picture.getvalue()).decode("ascii")
    raw = f"![Plot](data:image/png;base64,{payload})"

    sections = extract_markdown(raw.encode())

    assert _view(sections) == [("image", None, None, None, "[Image: Plot]")]
    assert sections[0].media == picture.getvalue()
    assert sections[0].media_type == "image/png"
    assert sections[0].index == 0


def test_heading_path_keeps_the_middle_level():
    markdown = extract_markdown(
        "# Guide\n\n## Setup\n\n### Windows\n\nBody under windows.\n\n## Run\n\nAfter.\n".encode()
    )
    html = extract_html(
        b"""
        <h1>Guide</h1><h2>Setup</h2><h3>Windows</h3>
        <p>Body under windows.</p>
        <h2>Run</h2><p>After.</p>
        """
    )
    document = Document()
    document.add_paragraph("Guide", style="Heading 1")
    document.add_paragraph("Setup", style="Heading 2")
    document.add_paragraph("Windows", style="Heading 3")
    document.add_paragraph("Body under windows.")
    document.add_paragraph("Run", style="Heading 2")
    document.add_paragraph("After.")
    word = extract_docx(_docx_bytes(document))

    for sections in (markdown, html, word):
        assert [(section.title, section.headings, section.data) for section in sections] == [
            ("Guide", ["Setup", "Windows"], "Body under windows."),
            ("Guide", ["Run"], "After."),
        ]
        assert sections[0].heading == "Setup"
        assert sections[0].subheading == "Windows"
        assert sections[1].heading == "Run"
        assert sections[1].subheading is None


def test_outline_numbers_are_headings_and_a_short_underline_is_not():
    raw = "\n".join(
        [
            "1. Item stays a list",
            "",
            "1.1 Setup",
            "",
            "Body.",
            "",
            "1.1.1 Windows",
            "",
            "More.",
            "",
            "Guide",
            "===",
            "",
            "Still a paragraph.",
        ]
    )

    sections = extract_markdown(raw.encode())

    assert _view(sections) == [
        ("list", None, None, None, "1. Item stays a list"),
        ("text", None, None, None, "Body."),
        ("text", "Windows", None, None, "More."),
        ("text", "Windows", None, None, "Guide"),
        ("text", "Windows", None, None, "Still a paragraph."),
    ]
    assert {section.title for section in sections} == {"Setup"}


def test_docx_finds_inherited_same_size_and_capital_headings():
    document = Document()
    topic = document.styles.add_style("Topic", WD_STYLE_TYPE.PARAGRAPH)
    topic.base_style = document.styles["Heading 2"]
    document.add_paragraph("Guide", style="Heading 1")
    document.add_paragraph("Setup", style="Topic")
    document.add_paragraph("Under the topic.")

    same_size = Document()
    title = same_size.add_paragraph()
    title_run = title.add_run("Guide")
    title_run.bold = True
    title_run.font.size = Pt(16)
    setup = same_size.add_paragraph()
    setup.paragraph_format.space_before = Pt(12)
    setup_run = setup.add_run("Setup")
    setup_run.bold = True
    setup_run.font.size = Pt(11)
    body = same_size.add_paragraph()
    body_run = body.add_run("Then run it.")
    body_run.font.size = Pt(11)
    note = same_size.add_paragraph()
    note_run = note.add_run("Note")
    note_run.bold = True
    note_run.font.size = Pt(11)

    numbered = Document()
    heading = numbered.add_paragraph()
    number = heading.add_run("2 ")
    number.bold = False
    number.font.size = Pt(16)
    label = heading.add_run("Setup")
    label.bold = True
    label.font.size = Pt(16)
    numbered_body = numbered.add_paragraph()
    numbered_body_run = numbered_body.add_run("Under the numbered title.")
    numbered_body_run.font.size = Pt(11)

    capitals = Document()
    methods = capitals.add_paragraph()
    methods_run = methods.add_run("methods")
    methods_run.bold = True
    methods_run.font.size = Pt(16)
    methods_run.font.all_caps = True
    capitals_body = capitals.add_paragraph()
    capitals_body_run = capitals_body.add_run("Under the capital title.")
    capitals_body_run.font.size = Pt(11)

    contents = Document()
    contents.add_paragraph("Guide", style="Heading 1")
    contents.styles.add_style("TOC 1", WD_STYLE_TYPE.PARAGRAPH)
    entry = contents.add_paragraph("Setup", style="TOC 1")
    entry._element.get_or_add_pPr().append(
        parse_xml(f'<w:outlineLvl {nsdecls("w")} w:val="0"/>')
    )
    contents.add_paragraph("After the contents.")

    assert _view(extract_docx(_docx_bytes(document))) == [
        ("text", "Setup", None, None, "Under the topic."),
    ]
    assert _view(extract_docx(_docx_bytes(same_size))) == [
        ("text", "Setup", None, None, "Then run it."),
        ("text", "Setup", None, None, "Note"),
    ]
    assert extract_docx(_docx_bytes(same_size))[0].title == "Guide"
    assert _view(extract_docx(_docx_bytes(numbered))) == [
        ("text", "2 Setup", None, None, "Under the numbered title."),
    ]
    assert _view(extract_docx(_docx_bytes(capitals))) == [
        ("text", "METHODS", None, None, "Under the capital title."),
    ]
    assert _view(extract_docx(_docx_bytes(contents))) == [
        ("text", "Guide", None, None, "After the contents."),
    ]


def test_html_reads_roles_word_classes_and_bold_titles():
    raw = """
    <html><body>
      <div role="heading" aria-level="2">Setup</div>
      <p>Under the role.</p>
      <p class="MsoHeading1">Guide</p>
      <p>Under the word heading.</p>
      <p class="section-title">Details</p>
      <p>Under the class.</p>
      <p><b>Notes</b></p>
      <p>Under the bold line.</p>
    </body></html>
    """

    sections = extract_html(raw.encode())

    assert _view(sections) == [
        ("text", None, "Setup", None, "Under the role."),
        ("text", "Guide", None, None, "Under the word heading."),
        ("text", "Guide", "Details", None, "Under the class."),
        ("text", "Guide", "Notes", None, "Under the bold line."),
    ]


def test_pdf_ranks_heading_sizes_and_reads_outline_entries():
    ranked = extract_pdf(_ranked_heading_pdf_bytes())

    assert _view(ranked) == [
        ("text", None, None, 1, "Intro paragraph."),
        ("text", "Setup", None, 1, "Then run it."),
    ]
    assert {section.title for section in ranked} == {"Guide"}

    wrapped = extract_pdf(_wrapped_heading_pdf_bytes())

    assert _view(wrapped) == [
        ("text", "Annual results for the region", None, 1, "Body follows the wrapped title."),
    ]

    outlined = extract_pdf(_outlined_pdf_bytes())

    assert _view(outlined) == [
        ("text", "Methods", None, 1, "The method is described here."),
    ]

    repeated = extract_pdf(_running_title_pdf_bytes())

    assert all("Handbook" not in section.data for section in repeated)
    assert [section.data for section in repeated] == [
        "Page one text.",
        "Page two text.",
        "Page three text.",
    ]


def test_markdown_packages_a_table_that_contains_an_image():
    raw = "\n".join(
        [
            "Before.",
            "",
            "| Item | Picture |",
            "| --- | --- |",
            "| Plot | ![Plot](plot.png) |",
            "",
            "After.",
        ]
    )

    sections = extract_markdown(raw.encode())

    assert _view(sections) == [
        ("text", None, None, None, "Before."),
        (
            "table",
            None,
            None,
            None,
            "| Item | Picture |\n| --- | --- |\n| Plot | [Image: Plot] |",
        ),
        ("image", None, None, None, "[Image: Plot]"),
        ("text", None, None, None, "After."),
    ]
    assert all(section.kind != "complex" for section in sections)


def test_html_packages_mixed_tables():
    image = extract_html(
        b"""
        <p>Before.</p>
        <table><tr><td>Quarter</td><td><img alt="Plot"></td></tr></table>
        <p>After.</p>
        """
    )
    nested = extract_html(
        b"<table><tr><td><table><tr><td>Inside</td></tr></table></td></tr></table>"
    )
    chart = extract_html(
        b'<table><tr><td><svg class="chart" aria-label="Revenue"></svg></td></tr></table>'
    )

    assert _view(image) == [
        ("text", None, None, None, "Before."),
        ("table", None, None, None, "| Quarter | [Image: Plot] |\n| --- | --- |"),
        ("image", None, None, None, "[Image: Plot]"),
        ("text", None, None, None, "After."),
    ]
    assert _view(nested) == [("table", None, None, None, "| Inside |\n| --- |")]
    assert _view(chart) == [("chart", None, None, None, "[Chart: Revenue]")]
    layout = extract_html(
        b"""
        <table>
          <tr>
            <td>Label</td>
            <td><table><tr><td><img alt="Logo"></td></tr></table></td>
          </tr>
        </table>
        """
    )
    assert _view(layout) == [
        ("table", None, None, None, "| Label | [Complex] |\n| --- | --- |"),
        ("complex", None, None, None, "[Complex]"),
    ]
    leftover = layout[1]
    assert leftover.media_type == "text/html"
    assert leftover.media is not None
    assert b"Logo" in leftover.media
    assert b"Label" not in leftover.media


def test_docx_packages_a_table_that_contains_an_image_or_table():
    pictured = Document()
    pictured.add_paragraph("Before the table.")
    table = pictured.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Quarter"
    picture = io.BytesIO()
    PilImage.new("RGB", (80, 60), "red").save(picture, format="PNG")
    picture.seek(0)
    table.cell(0, 1).paragraphs[0].add_run().add_picture(picture, width=Inches(1))
    picture_sections = extract_docx(_docx_bytes(pictured))

    nested_document = Document()
    outer = nested_document.add_table(rows=1, cols=1)
    inner = outer.cell(0, 0).add_table(rows=1, cols=1)
    inner.cell(0, 0).text = "Inside"
    nested_sections = extract_docx(_docx_bytes(nested_document))

    assert [section.kind for section in picture_sections] == ["text", "table", "image"]
    assert "Quarter" in picture_sections[1].data
    picture = next(section for section in picture_sections if section.kind == "image")
    assert picture.media is not None and picture.media.startswith(b"\x89PNG")
    assert _view(nested_sections) == [("table", None, None, None, "| Inside |\n| --- |")]
    assert all(section.kind != "complex" for section in nested_sections)


def test_pdf_packages_a_table_that_contains_an_image():
    sections = extract_pdf(_table_image_pdf_bytes())
    tables = [section for section in sections if section.kind == "table"]
    images = [section for section in sections if section.kind == "image"]

    assert len(tables) == 1
    assert "Quarter" in tables[0].data
    assert tables[0].page == 1
    assert len(images) == 1
    assert images[0].media_type == "image/png"
    assert images[0].media is not None and images[0].media.startswith(b"\x89PNG")
    assert all(section.kind != "complex" for section in sections)
    assert any(section.data == "Before the table." for section in sections)
    assert all("Hidden in the picture" not in section.data for section in sections)


def test_markdown_strips_inline_markup_and_keeps_indented_code():
    raw = "\n".join(
        [
            "See **this** and _that_ plus `code`.",
            "",
            "> a quoted line",
            "> still quoted",
            "",
            "    indented_code()",
            "",
        ]
    )

    sections = extract_markdown(raw.encode())

    assert _view(sections) == [
        ("text", None, None, None, "See this and that plus code."),
        ("text", None, None, None, "a quoted line still quoted"),
        ("code", None, None, None, "indented_code()"),
    ]


def test_html_walks_nested_blocks_and_skips_comments():
    raw = """
    <html><body>
      <p>Hello <!-- secret note --> world</p>
      <blockquote><p>One.</p><p>Two.</p><ul><li>Hidden</li></ul></blockquote>
      <figure>
        <img alt="Pic">
        <p>Explanation stays.</p>
        <figcaption>Cap</figcaption>
      </figure>
      <div aria-hidden="true" class="paragraph">Hidden paragraph</div>
      <svg class="paragraph"></svg>
    </body></html>
    """

    sections = extract_html(raw.encode())

    assert _view(sections) == [
        ("text", None, None, None, "Hello world"),
        ("text", None, None, None, "One."),
        ("text", None, None, None, "Two."),
        ("list", None, None, None, "- Hidden"),
        ("image", None, None, None, "[Image: Cap]"),
        ("text", None, None, None, "Explanation stays."),
        ("image", None, None, None, "[Image]"),
    ]
    assert all(section.kind != "chart" for section in sections)


def test_html_keeps_definition_lists_figures_and_heading_images():
    raw = """
    <html><body>
      <h1>Guide</h1>
      <dl>
        <dt>Term</dt>
        <dd>Definition</dd>
        <dt>Other</dt>
        <dd>Alpha</dd>
        <dd>Beta</dd>
      </dl>
      <figure>
        <img alt="One">
        <img alt="Two">
        <figcaption>Front office</figcaption>
      </figure>
      <h2><img alt="In heading"></h2>
    </body></html>
    """

    sections = extract_html(raw.encode())

    assert _view(sections) == [
        ("list", "Guide", None, None, "- Term: Definition\n- Other: Alpha Beta"),
        ("image", "Guide", None, None, "[Image: Front office]"),
        ("image", "Guide", None, None, "[Image: Two]"),
        ("image", "Guide", None, None, "[Image: In heading]"),
    ]


def test_pdf_rejoins_a_hyphenated_word_and_keeps_a_figure_label():
    sections = extract_pdf(_hyphen_pdf_bytes())

    assert _view(sections) == [
        ("text", None, None, 1, "The package handles instal-lation across a wrapped line."),
    ]

    labelled = extract_pdf(_figure_lead_pdf_bytes())
    image = next(section for section in labelled if section.kind == "image")

    assert image.data == "[Image: Figure 1]"
    assert any(section.kind == "text" and len(section.data) > 160 for section in labelled)
    assert all(section.data != "Figure 1" for section in labelled)


def test_pdf_reads_a_framed_datasheet_page_as_prose_and_one_table():
    sections = extract_pdf(_framed_pdf_bytes())

    kinds = [section.kind for section in sections]
    assert kinds.count("table") == 1
    table = next(section for section in sections if section.kind == "table")
    assert table.data == (
        "Table 1 Land sizes\n"
        "| Series | Code | a |\n"
        "| --- | --- | --- |\n"
        "| GRM | 155 | 0.6 to 0.8 |\n"
        "| GRM | 18 | 0.6 to 1.0 |"
    )
    assert table.title == "Soldering and Mounting"
    assert table.headings == ["1. Mounting Position", "1-1. Land Design"]
    assert table.heading == "1. Mounting Position"
    assert table.subheading == "1-1. Land Design"

    texts = [section.data for section in sections if section.kind == "text"]
    assert "The products listed here are designed for consumer equipment." in texts
    assert "Rated voltage (DC) is shown in the rating." in texts
    assert all(not text.isdigit() for text in texts)
    assert all("|" not in text for text in texts)
    assert _ids_are_unique(sections)


def test_pdf_plain_numbered_lines_stay_list_items():
    sections = extract_pdf(_numbered_body_pdf_bytes())

    assert _view(sections) == [
        ("text", "Rating", None, 1, "Intro line."),
        ("list", "Rating", None, 1, "- Measure at the rated voltage.\n- Keep the probe steady."),
    ]


def test_heading_state_drops_a_leading_marker_glyph():
    from ragbytes.extract.sections import HeadingState

    state = HeadingState()
    state.apply(1, "■ Scope")
    state.apply(2, "※ Notes")

    assert state.headings == ["Scope", "Notes"]
    assert (state.heading, state.subheading) == ("Scope", "Notes")


def test_normalize_inline_folds_width_and_keeps_superscripts():
    from ragbytes.extract.render import normalize_inline

    assert normalize_inline("Package（Tape）：\u3000150℃ ・ Test") == "Package(Tape): 150°C ・ Test"
    assert normalize_inline("Area 10 mm² ( in mm )") == "Area 10 mm² (in mm)"


def _view(sections):
    return [
        (section.kind, section.heading, section.subheading, section.page, section.data)
        for section in sections
    ]


def _ids_are_unique(sections) -> bool:
    ids = [section.id for section in sections]
    return (
        len(ids) == len(set(ids))
        and all(section.file_id == "" for section in sections)
        and [section.index for section in sections] == list(range(len(sections)))
    )


def _set_list_level(paragraph, level: int) -> None:
    properties = paragraph._element.get_or_add_pPr()
    numbering = properties.find(qn("w:numPr"))
    if numbering is None:
        numbering = parse_xml(
            f'<w:numPr {nsdecls("w")}><w:ilvl w:val="{level}"/><w:numId w:val="1"/></w:numPr>'
        )
        properties.append(numbering)
        return
    ilvl = numbering.find(qn("w:ilvl"))
    if ilvl is None:
        numbering.append(parse_xml(f'<w:ilvl {nsdecls("w")} w:val="{level}"/>'))
        return
    ilvl.set(qn("w:val"), str(level))


def _docx_bytes(document: Document) -> bytes:
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _add_chart(document: Document) -> None:
    part = Part(
        PackURI("/word/charts/chart1.xml"),
        CONTENT_TYPE.DML_CHART,
        blob=_chart_xml(),
        package=document.part.package,
    )
    rel_id = document.part.relate_to(part, RELATIONSHIP_TYPE.CHART)
    paragraph = document.add_paragraph()
    paragraph._element.append(
        parse_xml(
            f"""
            <w:r {nsdecls("w", "wp", "a", "r", "c")}>
              <w:drawing>
                <wp:inline>
                  <wp:extent cx="5486400" cy="3200400"/>
                  <wp:docPr id="1" name="Chart 1"/>
                  <a:graphic>
                    <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">
                      <c:chart r:id="{rel_id}"/>
                    </a:graphicData>
                  </a:graphic>
                </wp:inline>
              </w:drawing>
            </w:r>
            """
        )
    )


def _chart_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <c:chart>
    <c:title>
      <c:tx><c:rich><a:p><a:r><a:t>Revenue</a:t></a:r></a:p></c:rich></c:tx>
    </c:title>
    <c:plotArea>
      <c:barChart>
        <c:ser>
          <c:tx><c:v>Sales</c:v></c:tx>
          <c:cat><c:strLit>
            <c:pt idx="0"><c:v>Jan</c:v></c:pt>
            <c:pt idx="1"><c:v>Feb</c:v></c:pt>
          </c:strLit></c:cat>
          <c:val><c:numLit>
            <c:pt idx="0"><c:v>10</c:v></c:pt>
            <c:pt idx="1"><c:v>12</c:v></c:pt>
          </c:numLit></c:val>
        </c:ser>
        <c:ser>
          <c:tx><c:v>Costs</c:v></c:tx>
          <c:cat><c:strLit>
            <c:pt idx="0"><c:v>Jan</c:v></c:pt>
            <c:pt idx="1"><c:v>Feb</c:v></c:pt>
          </c:strLit></c:cat>
          <c:val><c:numLit>
            <c:pt idx="0"><c:v>4</c:v></c:pt>
            <c:pt idx="1"><c:v>5</c:v></c:pt>
          </c:numLit></c:val>
        </c:ser>
      </c:barChart>
    </c:plotArea>
  </c:chart>
</c:chartSpace>
"""


def _wrapped_pdf_bytes() -> bytes:
    styles = getSampleStyleSheet()
    loose = ParagraphStyle(
        "LooseBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=11,
        leading=20,
        spaceAfter=12,
    )
    text = (
        "The extractor should keep this <font name=\"Helvetica-Bold\">marked</font> "
        "sentence together even when the PDF wraps it across several visual lines "
        "on the page. A second sentence stays in the same paragraph until a real "
        "paragraph break."
    )
    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=letter)
    document.build(
        [
            Paragraph(text, loose),
            Paragraph("Next paragraph starts after a normal gap and should stay separate.", loose),
        ]
    )
    return buffer.getvalue()


def _body_marker_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=letter)
    drawing.setFont("Helvetica-Bold", 11)
    drawing.drawString(72, 720, "Bring the package")
    drawing.setFont("Helvetica", 11)
    drawing.drawString(72, 680, "The count stays in the body.")
    drawing.drawString(72, 400, "12")
    drawing.setFont("Helvetica", 9)
    drawing.drawString(300, 20, "4")
    drawing.save()
    return buffer.getvalue()


def _nested_bullet_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=letter)
    drawing.setFont("Helvetica", 11)
    drawing.drawString(72, 720, "- Use pip")
    drawing.drawString(100, 700, "- Then test")
    drawing.drawString(72, 680, "- Run it")
    drawing.save()
    return buffer.getvalue()


def _tight_column_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=letter)
    drawing.setFont("Helvetica", 11)
    left_lines = [
        "The left column explains the installation steps",
        "and how the files are laid out on disk today",
        "with enough text to form its own column",
    ]
    right_lines = [
        "The right column explains how to run it",
        "and where its configuration file is stored",
        "after the left column has been read",
    ]
    y = 700
    for left, right in zip(left_lines, right_lines, strict=True):
        drawing.drawString(72, y, left)
        drawing.drawString(400, y, right)
        y -= 16
    drawing.save()
    return buffer.getvalue()


def _two_column_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    document = BaseDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0,
        rightMargin=0,
        topMargin=0,
        bottomMargin=0,
    )
    document.addPageTemplates(
        [
            PageTemplate(
                id="columns",
                frames=[
                    Frame(72, 72, 220, 640, id="left"),
                    Frame(330, 72, 220, 640, id="right"),
                ],
            )
        ]
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "ColumnBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=11,
        leading=14,
    )
    document.build(
        [
            Paragraph(
                "The left column explains the installation steps for the package "
                "and how the files are laid out on disk.",
                body,
            ),
            FrameBreak(),
            Paragraph(
                "The right column explains how to run the program after installation "
                "and where its configuration is stored.",
                body,
            ),
        ]
    )
    return buffer.getvalue()


def _figure_pdf_bytes() -> bytes:
    picture = io.BytesIO()
    PilImage.new("RGB", (120, 80), "red").save(picture, format="PNG")
    picture.seek(0)
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=letter)
    drawing.drawImage(ImageReader(picture), 100, 500, width=200, height=120, mask="auto")
    drawing.setFillColor(colors.white)
    drawing.setFont("Helvetica", 10)
    drawing.drawString(130, 550, "Hidden axis label")
    drawing.setFillColor(colors.black)
    drawing.setFont("Helvetica", 11)
    drawing.drawString(72, 460, "The caption sits below the figure.")
    drawing.save()
    return buffer.getvalue()


def _stamp_footer(canvas, _doc) -> None:
    canvas.setFont("Helvetica", 8)
    canvas.drawString(72, 28, "Company confidential")


def _listed_pdf_bytes() -> bytes:
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "ListBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=11,
        leading=14,
        spaceAfter=8,
    )
    bold = ParagraphStyle(
        "LowerBold",
        parent=body,
        fontName="Helvetica-Bold",
    )
    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=letter)
    document.build(
        [
            Paragraph("Bring:", body),
            Paragraph("- Use pip", body),
            Paragraph("- Then run it", body),
            Paragraph("continued from above stays in the paragraph.", bold),
        ]
    )
    return buffer.getvalue()


def _contents_and_shifting_footer_pdf_bytes() -> bytes:
    notice = "© Example Health 2026. All rights reserved. Subject to the terms of use."
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=letter)
    for number in (1, 2, 3, 4):
        drawing.setFont("Helvetica", 11)
        if number == 1:
            drawing.drawString(72, 700, "Contents")
            drawing.drawString(72, 680, "Overview " + "." * 60 + " 2")
            drawing.drawString(72, 664, "Method " + "." * 62 + " 3")
        else:
            drawing.drawString(72, 700, f"Overview text for page {number}.")
        drawing.setFont("Helvetica", 8)
        if number % 2:
            drawing.drawString(72, 30, f"{notice} Page {number} of 4")
        else:
            drawing.drawString(72, 30, notice)
            drawing.drawString(500, 18, "of 4")
        drawing.showPage()
    drawing.save()
    return buffer.getvalue()


def _footer_pdf_bytes() -> bytes:
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "PageBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=11,
        leading=14,
    )
    story = []
    for number in (1, 2, 3):
        story.append(Paragraph(f"Body text for page {number}.", body))
        if number < 3:
            story.append(PageBreak())
    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=letter)
    document.build(story, onFirstPage=_stamp_footer, onLaterPages=_stamp_footer)
    return buffer.getvalue()


def _table_image_pdf_bytes() -> bytes:
    picture = io.BytesIO()
    PilImage.new("RGB", (120, 80), "red").save(picture, format="PNG")
    picture.seek(0)
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=letter)
    drawing.setFont("Helvetica", 11)
    drawing.drawString(72, 720, "Before the table.")
    drawing.setStrokeColor(colors.black)
    drawing.rect(72, 560, 328, 120, stroke=1, fill=0)
    drawing.line(236, 560, 236, 680)
    drawing.line(72, 620, 400, 620)
    drawing.drawString(80, 640, "Quarter")
    drawing.drawString(250, 640, "Picture")
    drawing.drawImage(ImageReader(picture), 250, 570, width=80, height=40, mask="auto")
    drawing.setFillColor(colors.white)
    drawing.setFont("Helvetica", 8)
    drawing.drawString(258, 584, "Hidden in the picture")
    drawing.save()
    return buffer.getvalue()


def _hyphen_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=letter)
    drawing.setFont("Helvetica", 11)
    drawing.drawString(72, 720, "The package handles instal-")
    drawing.drawString(72, 706, "lation across a wrapped line.")
    drawing.save()
    return buffer.getvalue()


def _figure_lead_pdf_bytes() -> bytes:
    picture = io.BytesIO()
    PilImage.new("RGB", (120, 80), "red").save(picture, format="PNG")
    picture.seek(0)
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=letter)
    drawing.setFont("Helvetica", 11)
    drawing.drawString(72, 640, "Figure 1")
    drawing.drawImage(ImageReader(picture), 72, 500, width=160, height=100, mask="auto")
    drawing.drawString(
        72,
        460,
        "A much longer sentence follows the figure and should stay a paragraph of its "
        "own rather than becoming the caption, because a real paragraph is too long "
        "to be the picture label.",
    )
    drawing.save()
    return buffer.getvalue()


def _framed_pdf_bytes() -> bytes:
    """A datasheet-style page: a ruled frame, bold numbered titles, and one real table."""
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=letter)
    drawing.setStrokeColor(colors.black)
    drawing.rect(50, 60, 512, 700, stroke=1, fill=0)
    drawing.line(50, 732, 562, 732)
    drawing.rect(52, 689, 23, 12, stroke=1, fill=0)
    drawing.setFont("Helvetica-Bold", 12)
    drawing.drawString(58, 742, "Soldering and Mounting")
    drawing.setFont("Helvetica", 9)
    drawing.drawString(58, 715, "The products listed here are designed for consumer equipment.")
    drawing.setFont("Helvetica-Bold", 9)
    drawing.drawString(58, 692, "1. Mounting Position")
    drawing.setFont("Helvetica", 9)
    drawing.drawString(58, 680, "Rated voltage (DC) is shown in the rating.")
    drawing.setFont("Helvetica-Bold", 9)
    drawing.drawString(58, 660, "1-1. Land Design")
    drawing.setFont("Helvetica", 9)
    drawing.drawString(58, 640, "Table 1 Land sizes")
    columns = (72, 200, 300, 400)
    rows = (630, 610, 590, 570)
    for x in columns:
        drawing.line(x, rows[-1], x, rows[0])
    for y in rows:
        drawing.line(columns[0], y, columns[-1], y)
    cells = [["Series", "Code", "a"], ["GRM", "155", "0.6 to 0.8"], ["GRM", "18", "0.6 to 1.0"]]
    for row_index, row in enumerate(cells):
        for column_index, text in enumerate(row):
            drawing.drawString(columns[column_index] + 4, rows[row_index] - 14, text)
    drawing.setFont("Helvetica", 11)
    drawing.drawString(300, 40, "1")
    drawing.save()
    return buffer.getvalue()


def _numbered_body_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=letter)
    drawing.setFont("Helvetica-Bold", 14)
    drawing.drawString(72, 720, "Rating")
    drawing.setFont("Helvetica", 11)
    drawing.drawString(72, 690, "Intro line.")
    drawing.drawString(72, 670, "1. Measure at the rated voltage.")
    drawing.drawString(72, 656, "2. Keep the probe steady.")
    drawing.save()
    return buffer.getvalue()


def _ranked_heading_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=letter)
    drawing.setFont("Helvetica-Bold", 16)
    drawing.drawString(72, 720, "Guide")
    drawing.setFont("Helvetica", 11)
    drawing.drawString(72, 690, "Intro paragraph.")
    drawing.setFont("Helvetica-Bold", 13)
    drawing.drawString(72, 650, "Setup")
    drawing.setFont("Helvetica", 11)
    drawing.drawString(72, 620, "Then run it.")
    drawing.save()
    return buffer.getvalue()


def _wrapped_heading_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=letter)
    drawing.setFont("Helvetica-Bold", 16)
    drawing.drawString(72, 720, "Annual results for")
    drawing.drawString(72, 702, "the region")
    drawing.setFont("Helvetica", 11)
    drawing.drawString(72, 660, "Body follows the wrapped title.")
    drawing.save()
    return buffer.getvalue()


def _outlined_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=letter)
    drawing.bookmarkPage("methods")
    drawing.addOutlineEntry("Methods", "methods", level=0, closed=False)
    drawing.setFont("Helvetica", 11)
    drawing.drawString(72, 700, "Methods")
    drawing.drawString(72, 676, "The method is described here.")
    drawing.save()
    return buffer.getvalue()


def _running_title_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=letter)
    labels = ("one", "two", "three")
    for index, label in enumerate(labels):
        if index:
            drawing.showPage()
        drawing.setFont("Helvetica-Bold", 11)
        drawing.drawString(72, 692, "Handbook")
        drawing.setFont("Helvetica", 11)
        drawing.drawString(72, 640, f"Page {label} text.")
    drawing.save()
    return buffer.getvalue()


def _pdf_bytes() -> bytes:
    picture = io.BytesIO()
    PilImage.new("RGB", (120, 80), "red").save(picture, format="PNG")
    picture.seek(0)

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "DocTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        spaceAfter=12,
    )
    heading = ParagraphStyle(
        "DocHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        spaceAfter=8,
    )
    body = ParagraphStyle(
        "DocBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=10,
    )
    data = [["Quarter", "Revenue"], ["Q1", "10"], ["Q2", "12"]]
    table = Table(data)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
            ]
        )
    )

    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=letter)
    document.build(
        [
            Paragraph("Annual Report", title),
            Paragraph("First paragraph of the introduction.", body),
            Paragraph("Second paragraph stays separate.", body),
            Paragraph("Revenue", heading),
            Paragraph("Figures for the year follow.", body),
            table,
            Spacer(1, 12),
            Image(picture, width=1.5 * inch, height=1 * inch),
            Paragraph("The photo shows the office.", body),
        ]
    )
    return buffer.getvalue()
