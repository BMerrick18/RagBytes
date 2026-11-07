"""Run real documents through semantic chunking and report how the chunks came out.

Usage: python scripts/semantic_report.py FILE [FILE ...] [--style NAME] [--show N]

Needs RAGBYTES_OPENAI_API_KEY. Vectors are cached in .semantic_cache.json, so
a second run after changing a threshold makes no embedding calls.
"""

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

from ragbytes.chunk.semantic.embed import OpenAIEmbedder
from ragbytes.chunk.semantic.semantic import chunk_semantic
from ragbytes.chunk.semantic.styles import STYLES, Style
from ragbytes.config import settings
from ragbytes.extract.complex import prepare_for_chunking
from ragbytes.extract.registry import get_extractor

CACHE = Path(".semantic_cache.json")


class CachedEmbedder:
    """Embed through OpenAI, keeping every vector on disk by model and text."""

    def __init__(self, inner: OpenAIEmbedder) -> None:
        self.inner = inner
        self.vectors: dict[str, list[float]] = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        keys = [self._key(text) for text in texts]
        missing = list({key: text for key, text in zip(keys, texts) if key not in self.vectors}.items())
        if missing:
            fresh = self.inner.embed([text for _, text in missing])
            for (key, _), vector in zip(missing, fresh, strict=True):
                self.vectors[key] = vector
            CACHE.write_text(json.dumps(self.vectors))
        return [self.vectors[key] for key in keys]

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.inner.model}\n{text}".encode()).hexdigest()


def report(path: Path, embedder: CachedEmbedder, show: int, style: Style) -> None:
    sections = prepare_for_chunking(get_extractor(path.suffix)(path.read_bytes()))
    chunks = chunk_semantic(sections, filename=path.name, embedder=embedder, style=style)
    sizes = [len(chunk.content) for chunk in chunks if isinstance(chunk.content, str)]
    print(f"\n=== {path.name} ({style.name}): {len(sections)} sections, {len(chunks)} chunks ===")
    if sizes:
        quartiles = statistics.quantiles(sizes, n=4) if len(sizes) > 1 else [sizes[0]] * 3
        print(
            f"chars min={min(sizes)} p25={quartiles[0]:.0f} median={quartiles[1]:.0f} "
            f"p75={quartiles[2]:.0f} max={max(sizes)}"
        )
        print(
            f"under {style.min_chars}: {sum(size < style.min_chars for size in sizes)}   "
            f"over {style.max_chars}: {sum(size > style.max_chars for size in sizes)}"
        )
    for chunk in chunks[:show]:
        text = chunk.content if isinstance(chunk.content, str) else f"<{len(chunk.content)} bytes>"
        path_label = " > ".join(chunk.metadata.headings) or "(no heading)"
        preview = text.replace("\n", " | ")[:160]
        print(f"  #{chunk.metadata.chunk_number} [{len(text)}] {path_label}: {preview}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--style", choices=list(STYLES), default="balanced")
    parser.add_argument("--show", type=int, default=15, help="chunks to preview per file")
    args = parser.parse_args()
    key = settings.openai_api_key.get_secret_value().strip()
    if not key:
        sys.exit("Set RAGBYTES_OPENAI_API_KEY first.")
    embedder = CachedEmbedder(OpenAIEmbedder(key, model=settings.semantic_model))
    for path in args.files:
        report(path, embedder, args.show, STYLES[args.style])


if __name__ == "__main__":
    main()
