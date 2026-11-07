"""Write web/src/lib/cv-demo.json: how each available tier chunks the sample report, and why.

The home page animates this. Run it again after changing a chunker or the sample report:

    python scripts/build_cv_demo.py

Each step records why a section started a new chunk or joined the one before, using the
chunkers' own rules. The script fails if those steps stop matching the real chunks.
"""

import json
from pathlib import Path

from ragbytes.chunk import simple, structured
from ragbytes.chunk.assemble import titled_path
from ragbytes.chunk.registry import CHUNKERS
from ragbytes.extract.complex import prepare_for_chunking
from ragbytes.extract.registry import get_extractor
from ragbytes.schemas import Section

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "web" / "public" / "sample-report.docx"
OUTPUT = ROOT / "web" / "src" / "lib" / "cv-demo.json"
PREVIEW = 72


def _preview(text: str) -> str:
    line = text.strip().splitlines()[0].removeprefix("- ")
    if len(line) <= PREVIEW:
        return line
    return line[:PREVIEW].rsplit(" ", 1)[0] + "…"


def _basic_plan(sections: list[Section], position: dict[int, int]) -> list[dict]:
    """Mirror chunk_simple: 500-character windows, with figures kept whole."""
    records: list[dict] = []
    pending: list[tuple[Section, str]] = []
    previous: list[str] | None = None

    def flush() -> None:
        if not pending:
            return
        spans: list[tuple[int, int, Section]] = []
        cursor = 0
        for index, (section, text) in enumerate(pending):
            if index:
                cursor += 2
            spans.append((cursor, cursor + len(text), section))
            cursor += len(text)
        full = "\n\n".join(text for _, text in pending)
        start = 0
        while start < len(full):
            end = simple._window_end(full, start)
            indexes: list[int] = []
            for span_start, span_end, section in spans:
                if span_end <= start or span_start >= end:
                    continue
                index = position[section.index]
                if index not in indexes:
                    indexes.append(index)
            records.append(
                {
                    "sections": indexes,
                    "chars": end - start,
                    "reason": "first" if not records else "full",
                    "text": full[start:end],
                }
            )
            start = end
        pending.clear()

    for section in simple.prepared_sections(sections):
        if not section.data.strip():
            continue
        if section.kind in simple.WHOLE_KINDS:
            flush()
            records.append(
                {
                    "sections": [position[section.index]],
                    "chars": len(section.data.strip()),
                    "reason": "kept_whole",
                    "text": section.data.strip(),
                }
            )
            previous = simple.window_path(section)
            continue
        pending.append((section, simple.section_window_text(section, previous)))
        previous = simple.window_path(section)
    flush()
    return records


def _structured_steps(sections: list[Section], position: dict[int, int]) -> list[list[dict]]:
    """Mirror structured.chunk_structured, noting why each section joined or started a chunk."""
    flowing = [
        section
        for section in simple.prepared_sections(sections)
        if section.kind not in simple.WHOLE_KINDS and section.data.strip()
    ]
    blocks = structured._fitted(structured._blocks(flowing))
    groups: list[list[dict]] = []
    previous: list[str] | None = None
    started = False
    for block in blocks:
        same_path = previous == block.path
        if len(block.texts) == len(block.members):
            steps = []
            for offset, (member, text) in enumerate(zip(block.members, block.texts, strict=True)):
                if offset == 0:
                    if not started:
                        reason = "first"
                    elif same_path:
                        reason = "too_long"
                    else:
                        reason = "new_heading"
                else:
                    reason = "same_heading"
                steps.append(
                    {"sections": [position[member.index]], "chars": len(text), "reason": reason}
                )
        else:
            reason = "first" if not started else ("too_long" if same_path else "new_heading")
            steps = [
                {
                    "sections": [position[member.index] for member in block.members],
                    "chars": len(block.text),
                    "reason": reason,
                }
            ]
        groups.append(steps)
        previous = list(block.path)
        started = True
    return groups


STEPS = {"structured": _structured_steps}


def build_demo() -> dict:
    sections = prepare_for_chunking(get_extractor(SAMPLE.suffix)(SAMPLE.read_bytes()))
    position = {section.index: i for i, section in enumerate(sections)}
    demo = {
        "title": sections[0].title or sections[0].headings[0],
        "limits": {
            "chunk_size": simple.CHUNK_SIZE,
            "structured_chunk_size": structured.CHUNK_SIZE,
        },
        "sections": [
            {
                "heading": section.headings[-1] if section.headings else section.title,
                "kind": section.kind,
                "chars": len(section.data.strip()),
                "preview": _preview(section.data),
                "text": section.data.strip(),
            }
            for section in sections
        ],
        "tiers": {},
    }
    for name, chunker in CHUNKERS.items():
        # Semantic cuts depend on live embeddings, so the home page sketches that tier by hand.
        if name != "basic" and name not in STEPS:
            continue
        produced = list(chunker(sections, filename=SAMPLE.name))
        if name == "basic":
            plan = _basic_plan(sections, position)
            visible = [_chunk_text(chunk) for chunk in produced]
            if [item["text"] for item in plan] != visible:
                raise ValueError("basic: the character windows no longer match the chunker's output")
            demo["tiers"][name] = [
                {
                    "sections": item["sections"],
                    "chars": len(chunk.content) if isinstance(chunk.content, str) else item["chars"],
                    "headings": titled_path(chunk.metadata.title, chunk.metadata.headings),
                    "text": chunk.content if isinstance(chunk.content, str) else item["text"],
                    "steps": [{"sections": item["sections"], "chars": item["chars"], "reason": item["reason"]}],
                }
                for item, chunk in zip(plan, produced, strict=True)
            ]
            continue
        chunks = []
        for chunk in produced:
            covered = [i for i, section in enumerate(sections) if section.data.strip() in chunk.content]
            chunks.append(
                {
                    "sections": covered,
                    "chars": len(chunk.embed_text),
                    "headings": titled_path(chunk.metadata.title, chunk.metadata.headings),
                }
            )
        missing = set(range(len(sections))) - {i for chunk in chunks for i in chunk["sections"]}
        if missing:
            raise ValueError(f"{name}: sections {sorted(missing)} aren't wholly inside any chunk")
        steps = STEPS[name](sections, position)
        if [[i for step in group for i in step["sections"]] for group in steps] != [c["sections"] for c in chunks]:
            raise ValueError(f"{name}: the explained steps no longer match the chunker's output")
        for chunk, group in zip(chunks, steps):
            chunk["steps"] = group
        demo["tiers"][name] = chunks
    return demo


def _chunk_text(chunk) -> str:
    if isinstance(chunk.content, str):
        return chunk.content
    return chunk.embed_text.split("\n\n", 1)[-1]


def render(demo: dict) -> str:
    return json.dumps(demo, indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(render(build_demo()), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
