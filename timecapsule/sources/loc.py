"""Chronicling America (Library of Congress / NEH National Digital Newspaper Program).

Millions of digitized US newspaper pages, 1756-1963, each with ALTO OCR
(word positions + confidence) and IIIF page images. Pages are searched through
the loc.gov JSON API; OCR comes from the page's ALTO file.

API docs: https://www.loc.gov/apis/json-and-yaml/
Collection: https://www.loc.gov/collections/chronicling-america/
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Iterator
from urllib.parse import parse_qs, urlparse

from ..models import Page
from ..ocr.alto import parse_alto
from .http import get

SEARCH_URL = "https://www.loc.gov/collections/chronicling-america/"
RIGHTS = (
    "Library of Congress, Chronicling America. The Library is not aware of any copyright "
    "restrictions on these pages; images and OCR are freely reusable."
)
_TITLE_RE = re.compile(r"^Image (\d+) of (.+?), ([A-Z][a-z]+ \d{1,2}, \d{4})")


def search(query: str, start: str, end: str, rows: int = 40, page: int = 1) -> list[dict]:
    params = {
        "q": query, "dates": f"{start}/{end}", "dl": "page", "fo": "json",
        "c": rows, "sp": page, "at": "results,pagination",
    }
    raw = get(SEARCH_URL, params=params, min_interval=3.0, timeout=180)
    return json.loads(raw).get("results", [])


def _split_title(name: str) -> tuple[str, str]:
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", name)
    return (m.group(1), m.group(2)) if m else (name, "")


def _alto_url(result: dict) -> str | None:
    for u in result.get("image_url", []):
        if "word-coordinates-service" in u:
            seg = parse_qs(urlparse(u).query).get("segment", [None])[0]
            if seg:
                return "https://tile.loc.gov/storage-services" + seg
    return None


def _iiif_base(result: dict) -> str | None:
    for u in result.get("image_url", []):
        if "/image-services/iiif/" in u:
            return u.split("/full/")[0]
    return None


def page_from_result(result: dict, collection: str = "") -> Page | None:
    alto = _alto_url(result)
    m = _TITLE_RE.match(result.get("title", ""))
    if not alto or not m:
        return None
    seq, full_name, _ = m.groups()
    name, place = _split_title(full_name)
    blocks, conf = parse_alto(get(alto, min_interval=1.0))
    if not blocks:
        return None
    url = result["id"].replace("http://", "https://")
    return Page(
        id="loc:" + result.get("page_id", url),
        source="loc",
        newspaper=name,
        place=place,
        date=result["date"],
        page=int(seq),
        url=url,
        text="\n\n".join(b.text for b in blocks),
        language=(result.get("language") or ["english"])[0][:2],
        iiif=_iiif_base(result),
        ocr_confidence=conf,
        ocr_engine="NDNP ALTO (vendor OCR, Library of Congress)",
        rights=RIGHTS,
        collection=collection,
        blocks=blocks,
    )


def fetch(query: str, start: str, end: str, limit: int = 12, per_title: int = 2,
          collection: str = "", candidates: int = 60) -> Iterator[Page]:
    """Yield up to ``limit`` relevant pages, at most ``per_title`` per newspaper,
    so a collection reflects many papers and places instead of one big daily."""
    seen: Counter[str] = Counter()
    n = 0
    for r in search(query, start, end, rows=candidates):
        if n >= limit:
            break
        title = (r.get("partof_title") or [r.get("title", "")])[0]
        if seen[title] >= per_title:
            continue
        try:
            page = page_from_result(r, collection)
        except Exception as e:  # one bad page must not sink a whole harvest
            print(f"  ! skipped {r.get('id')}: {e}")
            continue
        if page:
            seen[title] += 1
            n += 1
            yield page
