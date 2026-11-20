"""Internet Archive newspaper collections (https://archive.org/details/newspapers).

Over a million digitized issues from around the world, each OCR'd by the
Internet Archive (Tesseract-based). We read the issue's full OCR text from
``archive.org`` itself; it has no page breaks, so citations point at the
issue and deep-link to the Archive's in-scan search for the quoted words.

Search API: https://archive.org/advancedsearch.php
"""

from __future__ import annotations

import html
import json
import re
from typing import Iterator

from ..models import Page
from .http import get

RIGHTS = (
    "Digitized by the Internet Archive. Published before 1931, so in the public domain in "
    "the United States; check the item page for any additional terms."
)
_PRE = re.compile(r"<pre>(.*?)</pre>", re.S)


def search(start: str, end: str, rows: int = 50, extra: str = "") -> list[dict]:
    q = f"collection:newspapers AND mediatype:texts AND date:[{start} TO {end}] AND language:(English OR eng)"
    if extra:
        q += f" AND ({extra})"
    params = {"q": q, "fl[]": ["identifier", "title", "date", "coverage"], "rows": rows,
              "output": "json", "sort[]": "date asc"}
    raw = get("https://archive.org/advancedsearch.php", params=params, min_interval=1.0)
    return json.loads(raw)["response"]["docs"]


def metadata(identifier: str) -> dict:
    return json.loads(get(f"https://archive.org/metadata/{identifier}", min_interval=1.0))


def issue_text(identifier: str, files: list[dict] | None = None) -> str:
    """Full OCR text of an item. Most items name it ``<id>_djvu.txt``; some
    (e.g. the Gazette of India) use another stem, found in the file list."""
    name = f"{identifier}_djvu.txt"
    if files is not None:
        name = next((f["name"] for f in files if f["name"].endswith("_djvu.txt")), name)
    raw = get(f"https://archive.org/stream/{identifier}/{name}", min_interval=1.5)
    m = _PRE.search(raw.decode("utf-8", "replace"))
    return html.unescape(m.group(1)) if m else ""


def fetch_items(identifiers: list[str], collection: str = "", source: str = "ia",
                newspaper: str | None = None, place: str = "", section: str = "",
                rights: str = RIGHTS) -> Iterator[Page]:
    """Yield specific Internet Archive items by identifier (e.g. ones already in your archive)."""
    for ident in identifiers:
        meta = metadata(ident)
        md = meta.get("metadata", {})
        text = issue_text(ident, meta.get("files", []))
        if not text:
            print(f"  ! no OCR text for {ident}")
            continue
        langs = md.get("language", "en")
        yield Page(
            id=f"{source}:{ident}",
            source=source,
            newspaper=newspaper or _name({"title": md.get("title", ident), "identifier": ident}),
            place=place or (md.get("coverage") or ""),
            date=(md.get("date") or "")[:10],
            page=None,
            url=f"https://archive.org/details/{ident}",
            text=text,
            language="+".join(langs) if isinstance(langs, list) else langs,
            ocr_engine=f"Internet Archive OCR ({md.get('ocr', 'unknown engine')})",
            rights=rights,
            collection=collection,
            section=section,
        )


def _name(doc: dict) -> str:
    title = re.sub(r"[\s:(]*\d{4}[-.]\d{2}[-.]\d{2}\)?.*$", "", doc.get("title", "")).strip()
    title = re.sub(r"\s+\d{1,2}[-_]\d{2}[-_]\d{4}$", "", title)
    return title or doc["identifier"]


def fetch(start: str, end: str, must_mention: list[str], limit: int = 4, collection: str = "",
          candidates: int = 80, min_hits: int = 3) -> Iterator[Page]:
    """Yield up to ``limit`` issues from different newspapers whose OCR mentions
    the topic at least ``min_hits`` times (IA metadata search is not full-text)."""
    pats = [re.compile(rf"\b{re.escape(t)}", re.I) for t in must_mention]
    seen_titles: set[str] = set()
    n = 0
    for doc in search(start, end, rows=candidates):
        if n >= limit:
            break
        name = _name(doc)
        if name in seen_titles:
            continue
        try:
            text = issue_text(doc["identifier"])
        except Exception as e:
            print(f"  ! skipped {doc['identifier']}: {e}")
            continue
        hits = sum(len(p.findall(text)) for p in pats)
        if hits < min_hits:
            continue
        seen_titles.add(name)
        n += 1
        date = (doc.get("date") or "")[:10]
        place = doc.get("coverage") or ""
        if isinstance(place, list):
            place = place[0]
        yield Page(
            id=f"ia:{doc['identifier']}",
            source="ia",
            newspaper=name,
            place=place,
            date=date,
            page=None,
            url=f"https://archive.org/details/{doc['identifier']}",
            text=text,
            ocr_engine="Internet Archive OCR (Tesseract)",
            rights=RIGHTS,
            collection=collection,
        )
