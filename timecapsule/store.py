"""Corpus storage: gzip'd JSON Lines, one record per page / chunk.

Plain files keep the corpus diffable, easy to share, and readable from any
language without this package.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Iterable, Iterator

from .models import Chunk, Page

DEFAULT_DIR = Path("data/corpus")


def write_jsonl(path: Path, records: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> Iterator[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def load_pages(directory: Path = DEFAULT_DIR) -> list[Page]:
    pages: dict[str, Page] = {}
    for p in sorted(Path(directory).glob("pages-*.jsonl.gz")):
        for d in read_jsonl(p):
            pages[d["id"]] = Page.from_dict(d)
    return list(pages.values())


def load_chunks(directory: Path = DEFAULT_DIR) -> list[Chunk]:
    """Load passages, chunking the harvested pages first if needed (or if stale)."""
    from .chunking import chunk_page

    path = Path(directory) / "chunks.jsonl.gz"
    page_files = list(Path(directory).glob("pages-*.jsonl.gz"))
    if not page_files and not path.exists():
        raise SystemExit(f"No corpus in {directory}. Run `timecapsule harvest` first.")
    if not path.exists() or max(p.stat().st_mtime for p in page_files) > path.stat().st_mtime:
        chunks = [c for p in load_pages(directory) for c in chunk_page(p)]
        write_jsonl(path, (c.to_dict() for c in chunks))
        return chunks
    return [Chunk.from_dict(d) for d in read_jsonl(path)]
