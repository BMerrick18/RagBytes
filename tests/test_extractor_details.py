import io

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Pt
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from ragbytes.extract import pdf as pdf_module
from ragbytes.extract.extractors import (
    extract_docx,
    extract_html,
    extract_markdown,
    extract_pdf,
    extract_text,
)


def _view(sections):
    return [(section.kind, section.headings, section.data) for section in sections]


def test_html_spreads_spanning_cells_across_their_columns():
    raw = """
    <table>
      <tr><th colspan="2">Name</th><th>Age</th></tr>
      <tr><td rowspan="2">Ann</td><td>Lee</td><td>30</td></tr>
      <tr><td>Ray</td><td>31</td></tr>
    </table>
    """

    sections = extract_html(raw.encode())

    assert _view(sections) == [
        (
            "table",
            [],
            "| Name | Name | Age |\n| --- | --- | --- |\n"
            "| Ann | Lee | 30 |\n| Ann | Ray | 31 |",
        )
    ]


def test_html_writes_long_text_spanning_columns_once():
    apps = "bash, LibreOffice, GIMP, Blender, Mozilla Firefox"
    raw = f"""
    <table>
      <tr><th>Layer</th><th>Kernel</th><th>Desktop</th><th>Server</th></tr>
      <tr><td>User mode</td><td colspan="3">{apps}</td></tr>
    </table>
    """

    sections = extract_html(raw.encode())

    assert sections[0].data.split("\n")[-1] == f"| User mode | {apps} |  |  |"


def test_html_keeps_the_table_caption_above_the_table():
    raw = """
    <table>
      <caption>Table 3: Fuse ratings by model</caption>
      <tr><th>Model</th><th>Fuse</th></tr>
      <tr><td>A1</td><td>5A</td></tr>
    </table>
    """

    sections = extract_html(raw.encode())

    assert _view(sections) == [
        ("table", [], "Table 3: Fuse ratings by model\n| Model | Fuse |\n| --- | --- |\n| A1 | 5A |")
    ]


def test_markdown_numbered_list_counts_up_and_nests():
    raw = b"Steps:\n\n1. Unplug the unit\n1. Remove the cover\n   - Keep the screws\n   1. Lift the panel\n   1. Set it aside\n1. Replace the fuse\n"

    sections = extract_markdown(raw)

    assert _view(sections) == [
        (
            "list",
            [],
            "Steps:\n1. Unplug the unit\n2. Remove the cover\n  - Keep the screws\n"
            "  1. Lift the panel\n  2. Set it aside\n3. Replace the fuse",
        )
    ]


def test_plain_text_numbered_list_keeps_its_numbers():
    sections = extract_text(b"Do this:\n\n3. Third\n4. Fourth\n")

    assert sections[0].data == "Do this:\n3. Third\n4. Fourth"


def test_html_ordered_list_follows_start_and_value():
    raw = """
    <ol start="4">
      <li>Fourth</li>
      <li>Fifth<ul><li>A note</li></ul></li>
      <li value="9">Ninth</li>
      <li>Tenth</li>
    </ol>
    """

    sections = extract_html(raw.encode())

    assert _view(sections) == [("list", [], "4. Fourth\n5. Fifth\n  - A note\n9. Ninth\n10. Tenth")]


def test_html_drops_citations_edit_links_and_hidden_text():
    raw = """
    <main>
      <h2>History<span class="mw-editsection">[edit]</span></h2>
      <p>Linux began in 1991.<sup class="reference">[1]</sup></p>
      <p style="display: none">Hidden note.</p>
      <div class="navbox">Related articles</div>
    </main>
    """

    sections = extract_html(raw.encode())

    assert _view(sections) == [("text", ["History"], "Linux began in 1991.")]


def test_html_keeps_preformatted_text_verbatim():
    raw = "<pre>def f():\n    return 1\n</pre>"

    sections = extract_html(raw.encode())

    assert _view(sections) == [("code", [], "def f():\n    return 1")]


def test_markdown_reads_footnotes_definitions_and_html_blocks():
    raw = (
        "# Notes\n"
        "\n"
        "Text with a note[^a] and ==marked== words \\*kept\\*.\n"
        "\n"
        "[^a]: The note.\n"
        "\n"
        "Term\n"
        ": First meaning\n"
        ": Second meaning\n"
        "\n"
        '<p align="center"><img src="logo.png" alt="Logo"></p>\n'
        "\n"
        "***\n"
        "\n"
        "*[HTML]: Hyper Text Markup Language\n"
    )

    sections = extract_markdown(raw.encode())

    assert _view(sections) == [
        ("text", ["Notes"], "Text with a note and marked words *kept*."),
        ("text", ["Notes"], "Footnote a: The note."),
        ("list", ["Notes"], "- Term: First meaning; Second meaning"),
        ("image", ["Notes"], "[Image: Logo]"),
    ]


def test_plain_text_reads_flush_titles_and_drops_page_chrome():
    raw = (
        "1. Introduction\n"
        "\n"
        "   The protocol is described\n"
        "   here in some detail.\n"
        "\n"
        "Masinter                    Informational                     [Page 1]\n"
        "\f\n"
        "RFC 2324                       HTCPCP/1.0                 1 April 1998\n"
        "\n"
        "   It continues on this page.\n"
        "\n"
        "Masinter                    Informational                     [Page 2]\n"
        "\f\n"
        "RFC 2324                       HTCPCP/1.0                 1 April 1998\n"
        "\n"
        "2. Methods\n"
        "\n"
        "   BREW starts the pot.\n"
        "\n"
        "Masinter                    Informational                     [Page 3]\n"
        "\f\n"
        "RFC 2324                       HTCPCP/1.0                 1 April 1998\n"
    )

    sections = extract_text(raw.encode())

    assert _view(sections) == [
        ("text", ["Introduction"], "The protocol is described here in some detail."),
        ("text", ["Introduction"], "It continues on this page."),
        ("text", ["Methods"], "BREW starts the pot."),
    ]


def test_docx_joins_a_drop_cap_and_drops_contents_fields():
    document = Document()
    contents = document.add_paragraph()
    contents._element.append(
        parse_xml(
            f'<w:r {nsdecls("w")}><w:instrText>TOC \\o "1-3"</w:instrText></w:r>'
        )
    )
    contents._element.append(parse_xml(f'<w:r {nsdecls("w")}><w:t>Intro 1</w:t></w:r>'))
    letter = document.add_paragraph("O")
    letter._element.get_or_add_pPr().append(
        parse_xml(f'<w:framePr {nsdecls("w")} w:dropCap="drop" w:lines="3"/>')
    )
    document.add_paragraph("nce upon a time.")
    buffer = io.BytesIO()
    document.save(buffer)

    sections = extract_docx(buffer.getvalue())

    assert _view(sections) == [("text", [], "Once upon a time.")]


def test_plain_text_keeps_a_compound_split_at_a_line_end():
    raw = "The Request-\nURI names the pot.\n"

    sections = extract_text(raw.encode())

    assert _view(sections) == [("text", [], "The Request-URI names the pot.")]


def test_pdf_leaves_out_text_its_clipping_path_hides():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 700, "Visible words stay in the text.")
    pdf.saveState()
    frame = pdf.beginPath()
    frame.rect(300, 100, 100, 100)
    pdf.clipPath(frame, stroke=0, fill=0)
    pdf.drawString(72, 650, "Clipped words never show.")
    pdf.restoreState()
    pdf.save()

    sections = extract_pdf(buffer.getvalue())

    assert [section.data for section in sections] == ["Visible words stay in the text."]


def test_pdf_joins_a_comma_set_in_another_font():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    x = 72
    for text, font in (("For an adult ", "Helvetica"), ("tooth", "Helvetica-Bold"), (", advise care.", "Helvetica")):
        pdf.setFont(font, 11)
        pdf.drawString(x, 700, text)
        x += stringWidth(text, font, 11)
    pdf.save()

    sections = extract_pdf(buffer.getvalue())

    assert [section.data for section in sections] == ["For an adult tooth, advise care."]


def test_pdf_author_names_above_an_email_are_not_a_heading():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(72, 720, "Pots Are All You Need")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(72, 690, "Jane Doe John Smith")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, 676, "{jane, john}@example.com")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, 640, "Abstract")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, 622, "We study pots of coffee and tea.")
    pdf.save()

    sections = extract_pdf(buffer.getvalue())

    assert [(section.title, section.headings, section.data) for section in sections] == [
        ("Pots Are All You Need", [], "Jane Doe John Smith {jane, john}@example.com"),
        ("Pots Are All You Need", ["Abstract"], "We study pots of coffee and tea."),
    ]


def test_pdf_bold_title_case_heads_a_section_and_a_sentence_does_not():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(72, 720, "Bring the package")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 680, "The count stays in the body.")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(72, 620, "Foreign Travel")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 600, "Staff must book tickets in advance.")
    pdf.save()

    sections = extract_pdf(buffer.getvalue())

    assert _view(sections) == [
        ("text", [], "Bring the package"),
        ("text", [], "The count stays in the body."),
        ("text", ["Foreign Travel"], "Staff must book tickets in advance."),
    ]


def test_pdf_a_wrapped_part_of_sentence_is_not_a_heading():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 720, "Part of the informal counselling process will be creating a Performance Improvement")
    pdf.drawString(72, 706, "Plan which will lay out goals for the employee.")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(72, 650, "Formal Capability Procedure")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 630, "This stage of the procedure is triggered later.")
    pdf.save()

    sections = extract_pdf(buffer.getvalue())
    paths = {tuple(section.headings) for section in sections}
    text = "\n".join(section.data for section in sections)

    assert not any("Part of the informal" in path for path in paths)
    assert ("Formal Capability Procedure",) in paths
    assert "Part of the informal counselling process" in text


def test_pdf_capital_titles_sit_above_mixed_case_of_the_same_size():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(72, 720, "ANNUAL LEAVE")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 700, "Staff take leave in days.")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(72, 650, "Carrying Over Leave")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 630, "Up to five days may be carried.")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(72, 580, "MATERNITY LEAVE")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 560, "Leave starts on the agreed date.")
    pdf.save()

    sections = extract_pdf(buffer.getvalue())
    paths = {tuple(section.headings) for section in sections}

    assert ("ANNUAL LEAVE", "Carrying Over Leave") in paths
    assert ("MATERNITY LEAVE",) in paths


def test_pdf_a_bold_title_followed_by_a_picture_still_heads_the_section():
    from PIL import Image as PilImage
    from reportlab.lib.utils import ImageReader

    picture = io.BytesIO()
    PilImage.new("RGB", (40, 20), "blue").save(picture, format="PNG")
    picture.seek(0)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(72, 720, "ANNUAL LEAVE")
    pdf.drawImage(ImageReader(picture), 72, 680, width=40, height=20, mask="auto")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 650, "Staff take leave in days.")
    pdf.save()

    sections = extract_pdf(buffer.getvalue())

    assert any(section.headings[:1] == ["ANNUAL LEAVE"] and "Staff take leave" in section.data for section in sections)


def test_pdf_drops_a_stamp_printed_on_every_page():
    from PIL import Image as PilImage
    from reportlab.lib.utils import ImageReader

    picture = io.BytesIO()
    PilImage.new("RGB", (16, 16), "navy").save(picture, format="PNG")
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    for number in range(3):
        picture.seek(0)
        pdf.drawImage(ImageReader(picture), 500, 750, width=16, height=16, mask="auto")
        pdf.setFont("Helvetica", 11)
        pdf.drawString(72, 700, f"Page body {number + 1}.")
        pdf.showPage()
    pdf.save()

    sections = extract_pdf(buffer.getvalue())

    assert not any(section.kind == "image" for section in sections)
    assert "Page body 1." in "\n".join(section.data for section in sections)


def test_pdf_diagram_labels_and_a_table_caption_are_not_headings():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(72, 720, "Parity Disk")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, 700, "Each stripe keeps one parity block beside the data blocks it covers.")
    pdf.drawString(72, 686, "The parity disk is written on every update to any data disk.")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, 650, "Cp")
    pdf.drawString(72, 620, "Dp")
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(72, 580, "Table 3: Capacity")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, 566, "Capacity falls by one disk in every stripe group.")
    pdf.save()

    sections = extract_pdf(buffer.getvalue())

    assert {tuple(section.headings) for section in sections} == {("Parity Disk",)}
    text = "\n".join(section.data for section in sections)
    assert "Cp" in text and "Dp" in text
    assert "Table 3: Capacity" in text


def test_pdf_a_cover_title_above_the_bookmarked_headings_is_the_document_title():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawString(72, 720, "Emergency Care Guide")
    pdf.bookmarkPage("prioritising")
    pdf.addOutlineEntry("Prioritising Calls", "prioritising", level=0)
    pdf.setFont("Helvetica", 18)
    pdf.drawString(72, 660, "Prioritising Calls")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, 640, "Sort each call into one of three categories of care.")
    pdf.showPage()
    pdf.bookmarkPage("categories")
    pdf.addOutlineEntry("Categories of Care", "categories", level=0)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(72, 720, "Categories of Care")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(72, 680, "Urgent Care")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, 660, "Severe pain that self care does not control.")
    pdf.save()

    sections = extract_pdf(buffer.getvalue())

    assert {section.title for section in sections} == {"Emergency Care Guide"}
    assert [section.headings for section in sections] == [
        ["Prioritising Calls"],
        ["Categories of Care", "Urgent Care"],
    ]


def test_markdown_readme_masthead_names_the_document_and_drops_its_badges():
    raw = """<p align="center">
  <a href="https://fast.example"><img src="logo.png" alt="FastAPI"></a>
</p>
<p align="center">
    <em>FastAPI framework, high performance</em>
</p>
<p align="center">
<a href="https://ci.example"><img src="test.svg" alt="Test"></a>
<a href="https://cov.example"><img src="coverage.svg" alt="Coverage"></a>
</p>

FastAPI is a web framework.

## Sponsors

<a href="https://one.example" title="Sponsor One"><img src="one.png"></a>
<a href="https://two.example" title="Sponsor Two"><img src="two.png"></a>
"""

    sections = extract_markdown(raw.encode())

    assert {section.title for section in sections} == {"FastAPI"}
    assert _view(sections) == [
        ("text", [], "FastAPI framework, high performance"),
        ("text", [], "FastAPI is a web framework."),
        ("image", ["Sponsors"], "[Image: Sponsor One]"),
        ("image", ["Sponsors"], "[Image: Sponsor Two]"),
    ]


def test_plain_text_reads_gutenberg_caps_and_numbered_titles():
    raw = (
        "*** START OF THE PROJECT GUTENBERG EBOOK STYLE ***\n"
        "\n"
        "THE ELEMENTS OF STYLE\n"
        "\n"
        "    Form the possessive as follows.\n"
        "\n"
        "1. Definitions.\n"
        "\n"
        "   License means the terms.\n"
        "\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK STYLE ***\n"
        "\n"
        "This licence is left out.\n"
    )

    sections = extract_text(raw.encode())

    assert _view(sections) == [
        ("text", [], "Form the possessive as follows."),
        ("text", ["Definitions"], "License means the terms."),
    ]
    assert {section.title for section in sections} == {"THE ELEMENTS OF STYLE"}


def test_pdf_moves_a_word_whose_box_misses_its_baseline():
    def word(text, x0, top, baseline):
        return {
            "text": text,
            "x0": x0,
            "x1": x0 + 20,
            "top": top,
            "bottom": top + 10,
            "size": 10,
            "chars": [{"matrix": (10, 0, 0, 10, x0, 800 - baseline)}],
        }

    class Page:
        height = 800

    words = [word("Let", 50, 100, 108), word("us", 75, 100, 108), word("H", 100, 107, 108), word("x", 50, 112, 120)]

    pdf_module._align_to_baselines(Page(), words)

    assert [round(item["top"], 1) for item in words] == [100.0, 100.0, 100.0, 112.0]


def _docx(document: Document) -> bytes:
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_docx_numbered_list_keeps_the_numbers_word_shows():
    document = Document()
    document.add_paragraph("Steps:")
    document.add_paragraph("Unplug the unit", style="List Number")
    document.add_paragraph("Remove the cover", style="List Number")
    document.add_paragraph("Keep the screws", style="List Bullet")
    document.add_paragraph("Replace the fuse", style="List Number")

    sections = extract_docx(_docx(document))

    assert _view(sections) == [
        ("list", [], "Steps:\n1. Unplug the unit\n2. Remove the cover\n- Keep the screws\n3. Replace the fuse")
    ]


def test_docx_reads_content_controls_and_insertions_but_not_deletions_or_the_contents_control():
    document = Document()
    body = document.element.body
    body.append(
        parse_xml(
            f'<w:sdt {nsdecls("w")}><w:sdtPr><w:docPartObj><w:docPartGallery w:val="Table of Contents"/>'
            f"</w:docPartObj></w:sdtPr><w:sdtContent><w:p><w:r><w:t>Contents</w:t></w:r></w:p></w:sdtContent></w:sdt>"
        )
    )
    body.append(
        parse_xml(
            f'<w:sdt {nsdecls("w")}><w:sdtContent><w:p><w:r><w:t>Inside a content control.</w:t></w:r></w:p>'
            f"</w:sdtContent></w:sdt>"
        )
    )
    body.append(
        parse_xml(
            f'<w:p {nsdecls("w")}><w:r><w:t xml:space="preserve">Fit the </w:t></w:r>'
            f'<w:del w:id="1" w:author="a"><w:r><w:delText>old </w:delText></w:r></w:del>'
            f'<w:ins w:id="2" w:author="a"><w:r><w:t xml:space="preserve">new </w:t></w:r></w:ins>'
            f"<w:r><w:t>fuse.</w:t></w:r></w:p>"
        )
    )

    sections = extract_docx(_docx(document))

    assert [section.data for section in sections] == ["Inside a content control.", "Fit the new fuse."]


def test_docx_reads_a_text_box_after_its_paragraph_once():
    document = Document()
    anchor = document.add_paragraph("Before the box.")
    box = '<w:txbxContent><w:p><w:r><w:t>Inside a text box.</w:t></w:r></w:p></w:txbxContent>'
    anchor._element.append(
        parse_xml(
            f'<w:r {nsdecls("w", "wp", "a")} '
            f'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
            f'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
            f'xmlns:v="urn:schemas-microsoft-com:vml"><mc:AlternateContent>'
            f'<mc:Choice Requires="wps"><w:drawing><wp:anchor><a:graphic>'
            f'<a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
            f"<wps:wsp><wps:txbx>{box}</wps:txbx></wps:wsp></a:graphicData></a:graphic></wp:anchor></w:drawing>"
            f"</mc:Choice><mc:Fallback><w:pict><v:shape><v:textbox>{box}</v:textbox></v:shape></w:pict>"
            f"</mc:Fallback></mc:AlternateContent></w:r>"
        )
    )
    document.add_paragraph("After the box.")

    sections = extract_docx(_docx(document))

    assert [section.data for section in sections] == ["Before the box.", "Inside a text box.", "After the box."]


def test_docx_footnote_follows_the_paragraph_that_refers_to_it():
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part

    document = Document()
    document.add_paragraph("Guide", style="Heading 1")
    cited = document.add_paragraph("Use a 5A fuse.")
    cited._element.append(parse_xml(f'<w:r {nsdecls("w")}><w:footnoteReference w:id="1"/></w:r>'))
    document.add_paragraph("Close the cover.")
    notes = (
        f'<w:footnotes {nsdecls("w")}>'
        '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
        '<w:footnote w:id="1"><w:p><w:r><w:t>Rated for 250 V.</w:t></w:r></w:p></w:footnote>'
        "</w:footnotes>"
    )
    part = Part(
        PackURI("/word/footnotes.xml"),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml",
        notes.encode(),
        document.part.package,
    )
    document.part.relate_to(part, RELATIONSHIP_TYPE.FOOTNOTES)

    sections = extract_docx(_docx(document))

    assert _view(sections) == [
        ("text", ["Guide"], "Use a 5A fuse."),
        ("text", ["Guide"], "Footnote 1: Rated for 250 V."),
        ("text", ["Guide"], "Close the cover."),
    ]


def test_docx_bold_body_size_title_without_spacing_heads_a_section():
    document = Document()
    title = document.add_paragraph()
    run = title.add_run("Disciplinary action")
    run.bold = True
    run.font.size = Pt(11)
    body = document.add_paragraph()
    body_run = body.add_run("A first written warning will be issued.")
    body_run.font.size = Pt(11)

    sections = extract_docx(_docx(document))

    assert _view(sections) == [
        ("text", ["Disciplinary action"], "A first written warning will be issued."),
    ]


def test_docx_a_short_title_before_a_list_heads_the_list():
    document = Document()
    document.add_paragraph("Examples of misconduct")
    document.add_paragraph("unauthorised absence", style="List Bullet")
    document.add_paragraph("poor timekeeping", style="List Bullet")

    sections = extract_docx(_docx(document))

    assert _view(sections) == [
        (
            "list",
            ["Examples of misconduct"],
            "- unauthorised absence\n- poor timekeeping",
        ),
    ]


def _word(text: str, x0: float, top: float, x1: float | None = None, bottom: float | None = None) -> dict:
    width = 6 * len(text)
    return {
        "text": text,
        "x0": x0,
        "x1": x1 if x1 is not None else x0 + width,
        "top": top,
        "bottom": bottom if bottom is not None else top + 8,
    }


def test_a_lone_figure_frame_keeps_the_labels_around_its_steps():
    from ragbytes.extract import pdf_drawings as drawings

    frame = (10, 10, 210, 160)
    steps = [(30, 40, 70, 70), (90, 40, 130, 70), (150, 40, 190, 70)]
    links = [(68, 52, 92, 56), (128, 52, 152, 56), (70, 54, 74, 58)]
    cluster = [frame, *steps, *links]
    words = [
        _word("IN+", 34, 46, 66, 64),
        _word("OUT", 94, 46, 126, 64),
        _word("GND", 154, 46, 186, 64),
        _word("Pin 1 is the non-inverting input.", 20, 120, 200, 132),
    ]
    drawing = drawings._as_diagram(cluster, drawings._union(cluster), words, set(links), cluster[:4], set())

    assert drawing is not None
    assert "Pin 1 is the non-inverting input." in drawing.text


def test_repeated_slide_frames_leave_the_bullets_out_of_the_diagram():
    from ragbytes.extract import pdf_drawings as drawings

    def slide(left: float) -> tuple[list, list]:
        frame = (left, 10, left + 180, 160)
        steps = [
            (left + 20, 30, left + 70, 60),
            (left + 20, 80, left + 70, 110),
            (left + 100, 50, left + 160, 90),
        ]
        links = [
            (left + 40, 58, left + 44, 82),
            (left + 68, 50, left + 102, 54),
            (left + 108, 70, left + 112, 86),
        ]
        words = [
            _word("Disk", left + 24, 36, left + 66, 54),
            _word("Parity", left + 24, 86, left + 66, 104),
            _word("XOR", left + 108, 60, left + 150, 80),
            _word("Keep a spare in the rack.", left + 20, 130, left + 170, 142),
        ]
        return [frame, *steps, *links], words

    left_cluster, left_words = slide(10)
    right_cluster, right_words = slide(220)
    shapes = [left_cluster[:4], right_cluster[:4]]
    slide_sizes = drawings._slide_sizes(shapes)
    drawing = drawings._as_diagram(
        left_cluster,
        drawings._union(left_cluster),
        left_words,
        set(left_cluster[4:]),
        shapes[0],
        slide_sizes,
    )

    assert slide_sizes
    assert drawing is not None
    assert "XOR" in drawing.text
    assert "Keep a spare" not in drawing.text


def test_a_numeric_arrowhead_cluster_is_not_a_flow():
    from ragbytes.extract import pdf_drawings as drawings

    bars = [(20 + index * 8, 40, 24 + index * 8, 44) for index in range(6)]
    region = (10, 10, 80, 80)
    cluster = [region, *bars]
    words = [_word(str(value), 20 + index * 8, 50) for index, value in enumerate((0, 5, 10, 15, 20, 25))]

    assert drawings._as_flow(cluster, region, words) is None
