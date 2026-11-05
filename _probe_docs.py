"""One-off probe of test_documents through extract + chunk."""

import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ragbytes.chunk.simple import chunk_simple
from ragbytes.extract.complex import prepare_for_chunking
from ragbytes.extract.registry import get_extractor

ROOT = Path(__file__).parent / "test_documents"
FILES = [
    "Linux - Wikipedia.html",
    "dental checks.pdf",
    "sdcep practice guidance.pdf",
    "mouser test file.pdf",
]


def summarize(name: str) -> None:
    path = ROOT / name
    extractor = get_extractor(path.suffix)
    print(f"\n=== {name} ({path.stat().st_size} bytes) ===")
    raw = path.read_bytes()
    sections = extractor(raw)
    sections = prepare_for_chunking(sections)
    chunks = chunk_simple(sections, filename=name)
    kinds = Counter(s.kind for s in sections)
    print(f"sections={len(sections)} kinds={dict(kinds)} chunks={len(chunks)}")
    print(f"images_with_media={sum(1 for s in sections if s.kind == 'image' and s.media)}")
    print(f"complex={sum(1 for s in sections if s.kind == 'complex')}")
    headings = []
    for s in sections:
        if s.heading and s.heading not in headings:
            headings.append(s.heading)
        if s.subheading and s.subheading not in headings:
            headings.append(s.subheading)
    print("sample headings:", headings[:25])
    print("-- first 25 --")
    for s in sections[:25]:
        preview = s.data.replace("\n", " | ")[:140]
        print(f"  [{s.kind} p={s.page} h={s.heading!r}/{s.subheading!r}] {preview}")
    print("-- last 8 --")
    for s in sections[-8:]:
        preview = s.data.replace("\n", " | ")[:140]
        print(f"  [{s.kind} p={s.page} h={s.heading!r}/{s.subheading!r}] {preview}")
    empties = [s for s in sections if not s.data.strip()]
    print(f"empty_data={len(empties)}")
    embed_missing = [c for c in chunks if not c.embed_text.strip()]
    print(f"chunks_empty_embed={len(embed_missing)}")


if __name__ == "__main__":
    for name in FILES:
        summarize(name)
