"""Build the research corpus from ``corpus/collections.json``.

Each collection is an event with a date window. For each one we pull relevant
pages from Chronicling America (ALTO OCR, region-level citations) and whole
issues from the Internet Archive (issue-level citations), then save them to
``data/corpus/pages-<collection>.jsonl.gz``. Re-running skips finished
collections unless ``force`` is set; HTTP responses are cached on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

from .sources import headlines, internet_archive, loc
from .store import DEFAULT_DIR, write_jsonl

COLLECTIONS_FILE = Path("corpus/collections.json")


def load_collections(path: Path = COLLECTIONS_FILE) -> list[dict]:
    return json.loads(Path(path).read_text())


def harvest(only: list[str] | None = None, loc_pages: int = 12, ia_issues: int = 4,
            out_dir: Path = DEFAULT_DIR, force: bool = False) -> None:
    for col in load_collections():
        if only and col["id"] not in only:
            continue
        out = Path(out_dir) / f"pages-{col['id']}.jsonl.gz"
        if out.exists() and not force:
            print(f"= {col['id']}: already harvested")
            continue
        print(f"> {col['id']} ({col['start']} .. {col['end']})")
        pages = []
        if col.get("headlines_file"):
            pages += list(headlines.fetch(col["headlines_file"], collection=col["id"]))
            print(f"  headlines: {len(pages)} from Indian outlets")
        if col.get("ia_items"):
            for p in internet_archive.fetch_items(col["ia_items"], collection=col["id"], **col.get("ia_item_fields", {})):
                print(f"  item {p.date} {p.newspaper}: {len(p.text):,} characters of OCR")
                pages.append(p)
        for spec in col.get("india_samples", []):
            from .india import SOURCES as INDIA_SOURCES, fetch_sample

            src = next((x for x in INDIA_SOURCES if x["id"] == spec.get("source")), None) or spec
            for p in fetch_sample(src, spec["start"], spec["end"], col["id"], spec.get("per_decade", 1),
                                  spec.get("max_chars", 400_000), spec.get("kind", "ia"),
                                  spec.get("sort", "identifier asc"), spec.get("candidates", 6)):
                if any(q.id == p.id for q in pages):
                    continue  # the same issue picked by two sampling rules
                print(f"  india {p.date} {p.newspaper[:60]}: {len(p.text):,} chars")
                pages.append(p)
        if loc_pages and col.get("loc_query"):
            for p in loc.fetch(col["loc_query"], col["start"], col["end"], limit=loc_pages,
                               collection=col["id"]):
                print(f"  loc  {p.date} {p.newspaper} ({p.place}) seq {p.page}  conf={p.ocr_confidence}")
                pages.append(p)
        if ia_issues and col.get("ia_terms"):
            for p in internet_archive.fetch(col["start"], col["end"], col["ia_terms"], limit=ia_issues,
                                            collection=col["id"]):
                print(f"  ia   {p.date} {p.newspaper}")
                pages.append(p)
        n = write_jsonl(out, (p.to_dict() for p in pages))
        print(f"  saved {n} pages -> {out}")
