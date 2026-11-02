import re
from functools import cache
from pathlib import Path

import pytest

from shark_byte.extract.registry import get_extractor

DOCUMENTS = Path(__file__).resolve().parent.parent / "test_documents"
CORPUS = DOCUMENTS / "corpus"


@cache
def _sections(name: str):
    path = DOCUMENTS / name
    if not path.exists():
        pytest.skip(f"{name} is not in test_documents")
    return get_extractor(path.suffix)(path.read_bytes())


def _text(name: str) -> str:
    return "\n".join(section.data for section in _sections(name))


def _paths(name: str) -> set[tuple[str, ...]]:
    return {tuple(section.headings) for section in _sections(name)}


@pytest.mark.parametrize(
    "name",
    sorted(path.name for path in DOCUMENTS.glob("*.*")) if DOCUMENTS.exists() else [],
)
def test_every_document_extracts_clean_sections(name):
    sections = _sections(name)

    assert sections
    assert [section.index for section in sections] == list(range(len(sections)))
    for section in sections:
        assert section.data.strip() or section.media
        assert "\ufffd" not in section.data
        assert not re.search(r"[\ue000-\uf8ff]", section.data)


def test_resnet_reads_columns_in_order_with_a_heading_tree():
    name = "resnet two column paper.pdf"
    paths = _paths(name)
    text = _text(name)

    title = "Deep Residual Learning for Image Recognition"
    assert (title, "3. Deep Residual Learning", "3.1. Residual Learning") in paths
    assert (title, "4. Experiments", "4.2. CIFAR-10 and Analysis") in paths
    assert "Deeper neural networks are more difficult to train." in text
    assert "residual learning framework to ease the training" in text
    assert not any("Kaiming He" in path for path in paths)
    assert "Let us consider H(x) as an underlying mapping" in text
    assert "y = F (x, {Wi}) + x. (1)" in text


def test_slide_deck_drops_the_clipped_copy_of_each_slide():
    text = _text("lecture slide deck.pdf")

    assert ("Just a bunch of disks (JBOD)",) in _paths("lecture slide deck.pdf")
    assert not re.search(r"\b([A-Za-z]{3,})\1\b", text)
    assert "Write both, read either" in text
    assert "ARPACI" not in text


def test_sdcep_keeps_lists_and_the_flowchart_as_an_image():
    name = "sdcep practice guidance.pdf"
    sections = _sections(name)

    assert ("Categories of care", "Emergency Care") in _paths(name)
    lists = [section for section in sections if section.kind == "list"]
    assert lists and all(
        re.search(r"^- \S", section.data, re.M) for section in lists
    )
    assert "adult tooth, advise immediate reimplantation" in _text(name)
    flowcharts = [
        section
        for section in sections
        if section.kind == "image" and section.page == 3 and section.media
    ]
    assert flowcharts


def test_nice_guideline_joins_cross_page_text_and_drops_page_chrome():
    name = "dental checks.pdf"
    text = _text(name)

    assert ("Dental checks: intervals between oral health reviews", "Recommendations") in (
        _paths(name)
    )
    assert "Page " not in text
    assert not re.search(r"^1\.1\.\d+$", text, re.M)


def test_scanned_page_is_one_complex_section():
    sections = _sections("scanned page.pdf")

    assert [section.kind for section in sections] == ["complex"]
    assert sections[0].media


def test_wikipedia_drops_citations_and_edit_links():
    text = _text("Linux - Wikipedia.html")

    assert not re.search(r"\[\d+\]", text)
    assert "[edit]" not in text
    assert "Jump to content" not in text


def test_rfc_drops_page_chrome_and_builds_a_heading_tree():
    name = "rfc2324 coffee pot protocol.txt"
    text = _text(name)

    assert "[Page " not in text
    assert "\f" not in text
    assert "Request- URI" not in text
    assert ("HTCPCP Protocol", "HTCPCP return codes", "418 I'm a teapot") in _paths(name)
    assert any(section.kind == "code" for section in _sections(name))


def test_markdown_sample_reads_footnotes_and_definitions():
    name = "markdown syntax sample.md"
    text = _text(name)

    assert "Footnote first: Footnote can have markup" in text
    assert "- Term 1: Definition 1" in text
    assert "[^" not in text
    assert ":::" not in text


def test_calibre_docx_joins_the_drop_cap_and_drops_contents_lines():
    text = _text("calibre demo.docx")

    assert "Drop caps are used to emphasize" in text
    assert "Text Formatting 2" not in text


def _corpus(name: str):
    path = CORPUS / name
    if not path.exists():
        pytest.skip(f"{name} is not in test_documents/corpus")
    return get_extractor(path.suffix)(path.read_bytes())


def test_corpus_think_python_builds_a_chapter_tree():
    sections = _corpus("textbook - think python chapter.html")
    paths = {tuple(section.headings) for section in sections}

    assert ("Chapter 3 Functions", "3.1 Function calls") in paths
    assert ("Chapter 3 Functions", "3.14 Exercises") in paths


def test_corpus_apache_license_reads_the_definitions_clause():
    sections = _corpus("legal - apache license.txt")
    text = "\n".join(section.data for section in sections)

    assert any(
        section.headings[-1:] == ["Definitions"] for section in sections if section.headings
    )
    assert "Grant of Copyright License" in text


def test_corpus_bert_keeps_the_paper_title_and_authors_as_text():
    sections = _corpus("study - bert.pdf")

    assert sections[0].headings == [
        "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding"
    ]
    assert "Jacob Devlin" in sections[0].data
    assert "Jacob Devlin" not in "".join(sections[0].headings)


def test_corpus_outdoors_handbook_keeps_a_policy_tree():
    sections = _corpus("policy - outdoors group employee handbook.pdf")
    paths = {tuple(section.headings) for section in sections}
    text = "\n".join(section.data for section in sections)

    assert ("Handbook", "Absence Management", "Aim") in paths
    assert not any("Part-time employees receive" in path for path in paths)
    assert "Part-time employees receive a pro-rated entitlement" in text
