"""Chunk the harvested pages and export the static data the website searches.

Site data is split per collection and normalized (page metadata is stored once,
passages point at it) to keep downloads small. Passages whose OCR is too
damaged to be useful in a browser (quality below ``SITE_MIN_QUALITY``) are kept
in the full corpus for the Python tools but left out of the site.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

from .chunking import chunk_page
from .harvest import load_collections
from .models import Chunk
from .store import DEFAULT_DIR, load_pages, write_jsonl

SITE_DATA = Path("site/data")
SITE_MIN_QUALITY = 0.5
# Internet Archive items are whole issues with no layout. On the website we keep
# the passages within this many windows of a mention of the event, which keeps
# downloads small; the full issues stay in the Python corpus.
IA_CONTEXT_WINDOWS = 2

SOURCES = {
    "loc": {
        "name": "Chronicling America",
        "publisher": "Library of Congress & National Endowment for the Humanities (NDNP)",
        "url": "https://www.loc.gov/collections/chronicling-america/",
    },
    "ia": {
        "name": "Internet Archive Newspapers",
        "publisher": "Internet Archive",
        "url": "https://archive.org/details/newspapers",
    },
    "headline": {
        "name": "Indian news headlines (project archive)",
        "publisher": "Headlines and links from Indian outlets, collected August 2020",
        "url": "",
    },
    "gazette": {
        "name": "The Gazette of India",
        "publisher": "Government of India; digitized by Public.Resource.Org and the Internet Archive",
        "url": "https://archive.org/details/gazetteofindia",
    },
    "local": {"name": "Local scans", "publisher": "Contributed scans, OCR'd with Tesseract", "url": ""},
}


def build(corpus_dir: Path = DEFAULT_DIR, site_dir: Path = SITE_DATA) -> list[Chunk]:
    pages = load_pages(corpus_dir)
    chunks = [c for p in pages for c in chunk_page(p)]
    n = write_jsonl(Path(corpus_dir) / "chunks.jsonl.gz", (c.to_dict() for c in chunks))
    print(f"{len(pages)} pages -> {n} passages -> {Path(corpus_dir) / 'chunks.jsonl.gz'}")
    export_site(pages, chunks, site_dir)
    return chunks


def _site_selection(chunks: list[Chunk], cols: dict[str, dict]) -> list[bool]:
    keep = [c.quality >= SITE_MIN_QUALITY for c in chunks]
    by_page: dict[str, list[int]] = {}
    for i, c in enumerate(chunks):
        if c.source == "ia":
            by_page.setdefault(c.page_id, []).append(i)
    for idxs in by_page.values():
        terms = cols.get(chunks[idxs[0]].collection, {}).get("ia_terms", [])
        pat = re.compile("|".join(rf"\b{re.escape(t)}" for t in terms), re.I) if terms else None
        hits = [j for j, i in enumerate(idxs) if pat and pat.search(chunks[i].text)]
        near = {j + d for j in hits for d in range(-IA_CONTEXT_WINDOWS, IA_CONTEXT_WINDOWS + 1)}
        for j, i in enumerate(idxs):
            keep[i] = keep[i] and j in near
    return keep


def export_site(pages, chunks: list[Chunk], site_dir: Path = SITE_DATA) -> None:
    site_dir = Path(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    for old in site_dir.glob("shard-*.json"):
        old.unlink()
    collections = load_collections()
    keep = _site_selection(chunks, {c["id"]: c for c in collections})
    by_col: dict[str, list[Chunk]] = {}
    for c, k in zip(chunks, keep):
        if k:
            by_col.setdefault(c.collection or "uncollected", []).append(c)
    page_meta = {p.id: p for p in pages}

    manifest_cols = []
    total_passages = 0
    for col in collections + [{"id": "uncollected", "title": "Other material"}]:
        cid = col["id"]
        cs = by_col.get(cid, [])
        if not cs:
            continue
        page_ids = sorted({c.page_id for c in cs})
        idx = {pid: i for i, pid in enumerate(page_ids)}
        shard_pages = []
        for pid in page_ids:
            p = page_meta[pid]
            entry = {
                "id": pid, "src": p.source, "paper": p.newspaper, "place": p.place, "date": p.date,
                "seq": p.page, "url": p.url, "iiif": p.iiif, "sec": p.section,
            }
            shard_pages.append({k: v for k, v in entry.items() if v not in (None, "")})  # keep shards small
        shard_chunks = [[idx[c.page_id], c.text, list(c.bbox) if c.bbox else None, c.quality] for c in cs]
        fname = f"shard-{cid}.json"
        (site_dir / fname).write_text(json.dumps({"pages": shard_pages, "chunks": shard_chunks},
                                                 ensure_ascii=False, separators=(",", ":")))
        col_pages = [page_meta[pid] for pid in page_ids]
        manifest_cols.append({
            **col,
            "file": fname,
            "stats": {
                "pages": len(col_pages),
                "passages": len(cs),
                "newspapers": len({p.newspaper for p in col_pages}),
                "places": sorted({p.place for p in col_pages if p.place}),
                "sources": dict(Counter(p.source for p in col_pages)),
                "dates": [min(p.date for p in col_pages), max(p.date for p in col_pages)],
            },
            "titles": sorted({f"{p.newspaper}|{p.place}|{p.source}" for p in col_pages}),
        })
        total_passages += len(cs)

    manifest = {
        "built": date.today().isoformat(),
        "min_quality": SITE_MIN_QUALITY,
        "sources": SOURCES,
        "totals": {
            "pages": len(pages),
            "passages": total_passages,
            "newspapers": len({p.newspaper for p in pages}),
            "places": len({p.place for p in pages if p.place}),
            "scanned": sum(p.source != "headline" for p in pages),
            "scanned_titles": len({p.newspaper for p in pages if p.source != "headline"}),
            "headlines": sum(p.source == "headline" for p in pages),
            "outlets": len({p.newspaper for p in pages if p.source == "headline"}),
        },
        "collections": manifest_cols,
    }
    (site_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    size = sum(f.stat().st_size for f in site_dir.glob("*.json")) / 1e6
    print(f"site data: {len(manifest_cols)} collections, {total_passages} passages, {size:.1f} MB -> {site_dir}")
