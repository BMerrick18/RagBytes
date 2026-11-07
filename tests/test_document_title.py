from ragbytes.chunk.semantic.semantic import chunk_semantic
from ragbytes.chunk.simple import chunk_simple
from ragbytes.chunk.structured import chunk_structured
from ragbytes.extract.extractors import extract_markdown

CV = b"""# Jane Smith

jane@example.com | London

## Experience

Senior Engineer at Acme, 2020 to now.

## Education

BSc Computer Science, University of Leeds.
"""


class _Embedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def test_a_cv_name_is_the_title_and_its_sections_are_the_headings():
    sections = extract_markdown(CV)

    assert [(section.title, section.headings, section.heading, section.subheading) for section in sections] == [
        ("Jane Smith", [], None, None),
        ("Jane Smith", ["Experience"], "Experience", None),
        ("Jane Smith", ["Education"], "Education", None),
    ]


def test_structured_chunks_carry_the_title_in_metadata_and_embed_text():
    chunks = chunk_structured(extract_markdown(CV), filename="cv.md")

    assert [(chunk.metadata.title, chunk.metadata.headings, chunk.metadata.heading) for chunk in chunks] == [
        ("Jane Smith", [], None),
        ("Jane Smith", ["Experience"], "Experience"),
        ("Jane Smith", ["Education"], "Education"),
    ]
    assert [chunk.embed_text.split("\n\n")[0] for chunk in chunks] == [
        "Jane Smith",
        "Jane Smith > Experience",
        "Jane Smith > Education",
    ]


def test_basic_chunks_still_write_the_title_into_the_text():
    chunks = chunk_simple(extract_markdown(CV), filename="cv.md")

    assert chunks[0].content.startswith("Jane Smith\n\njane@example.com")
    assert chunks[0].content.count("Jane Smith") == 1
    assert {chunk.metadata.title for chunk in chunks} == {"Jane Smith"}


def test_semantic_chunks_keep_the_title_when_small_sections_share_a_chunk():
    chunks = chunk_semantic(extract_markdown(CV), filename="cv.md", embedder=_Embedder())

    assert {chunk.metadata.title for chunk in chunks} == {"Jane Smith"}
    assert all(chunk.embed_text.startswith("Jane Smith") for chunk in chunks)
    assert all(chunk.metadata.heading != "Jane Smith" for chunk in chunks)
    assert "Experience" in "\n".join(chunk.embed_text for chunk in chunks)


def test_two_top_level_headings_are_not_a_title():
    sections = extract_markdown(b"# Install\n\nRun it.\n\n## Windows\n\nClick.\n\n# Configure\n\nEdit it.\n")

    assert {section.title for section in sections} == {None}
    assert [section.headings for section in sections] == [["Install"], ["Install", "Windows"], ["Configure"]]


def test_a_title_repeated_in_another_case_is_still_the_title():
    sections = extract_markdown(
        b"# Dental Checks\n\nIntro.\n\n## Overview\n\nText.\n\n# DENTAL CHECKS\n\n## Pain\n\nMore.\n"
    )

    assert {section.title for section in sections} == {"Dental Checks"}
    assert [section.headings for section in sections] == [[], ["Overview"], ["Pain"]]


def test_a_lone_heading_with_nothing_under_it_stays_a_heading():
    sections = extract_markdown(b"# Notes\n\nOne paragraph.\n\nAnother paragraph.\n")

    assert {section.title for section in sections} == {None}
    assert {section.heading for section in sections} == {"Notes"}
