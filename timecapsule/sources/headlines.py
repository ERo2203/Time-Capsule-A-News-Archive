"""Import a news-headline dataset, keeping the Indian press.

The original version of this project collected ~108,000 English headlines
(August 2020) as JSON records like::

    {"topic": "NATION", "link": "https://timesofindia.indiatimes.com/...",
     "domain": "timesofindia.indiatimes.com", "published_date": "2020-08-08 14:33:00",
     "title": "...", "lang": "en"}

This connector reads that file (or the zip it ships in), keeps the headlines from
Indian outlets, and turns each into a citable record: outlet, date, section
and a link to the article. Only the headline and link are stored; the article
text stays with its publisher.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Iterator

from ..models import Page

# Registrable domain -> (outlet name, home city). Longest match wins, so
# "mumbaimirror.indiatimes.com" is Mumbai Mirror, not Indiatimes.
INDIAN_OUTLETS: dict[str, tuple[str, str]] = {
    "timesofindia.indiatimes.com": ("The Times of India", "Mumbai"),
    "economictimes.indiatimes.com": ("The Economic Times", "Mumbai"),
    "mumbaimirror.indiatimes.com": ("Mumbai Mirror", "Mumbai"),
    "bangaloremirror.indiatimes.com": ("Bangalore Mirror", "Bengaluru"),
    "indiatimes.com": ("Indiatimes", ""),
    "indianexpress.com": ("The Indian Express", "New Delhi"),
    "newindianexpress.com": ("The New Indian Express", "Chennai"),
    "financialexpress.com": ("The Financial Express", "Mumbai"),
    "ndtv.com": ("NDTV", "New Delhi"),
    "news18.com": ("News18", "Noida"),
    "livemint.com": ("Mint", "New Delhi"),
    "moneycontrol.com": ("Moneycontrol", "Mumbai"),
    "pinkvilla.com": ("Pinkvilla", "Mumbai"),
    "deccanherald.com": ("Deccan Herald", "Bengaluru"),
    "deccanchronicle.com": ("Deccan Chronicle", "Hyderabad"),
    "firstpost.com": ("Firstpost", "Mumbai"),
    "timesnownews.com": ("Times Now", "Mumbai"),
    "tribuneindia.com": ("The Tribune", "Chandigarh"),
    "indiatoday.in": ("India Today", "Noida"),
    "business-standard.com": ("Business Standard", "New Delhi"),
    "indiatvnews.com": ("India TV", "Noida"),
    "indiaglitz.com": ("IndiaGlitz", "Chennai"),
    "thehindu.com": ("The Hindu", "Chennai"),
    "thehindubusinessline.com": ("The Hindu BusinessLine", "Chennai"),
    "hindustantimes.com": ("Hindustan Times", "New Delhi"),
    "thenewsminute.com": ("The News Minute", "Bengaluru"),
    "india.com": ("India.com", ""),
    "zeenews.india.com": ("Zee News", "Noida"),
    "aninews.in": ("ANI (Asian News International)", "New Delhi"),
    "scroll.in": ("Scroll.in", ""),
    "bollywoodhungama.com": ("Bollywood Hungama", "Mumbai"),
    "wionews.com": ("WION", "Noida"),
    "businessinsider.in": ("Business Insider India", ""),
    "thewire.in": ("The Wire", "New Delhi"),
    "thequint.com": ("The Quint", "Noida"),
    "siasat.com": ("The Siasat Daily", "Hyderabad"),
    "cnbctv18.com": ("CNBC-TV18", "Mumbai"),
    "theprint.in": ("ThePrint", "New Delhi"),
    "nationalheraldindia.com": ("National Herald", "New Delhi"),
    "sentinelassam.com": ("The Sentinel", "Guwahati"),
    "theweek.in": ("The Week", "Kochi"),
    "mid-day.com": ("Mid-Day", "Mumbai"),
    "jagran.com": ("Dainik Jagran (English)", "Noida"),
    "oneindia.com": ("Oneindia", "Bengaluru"),
    "dnaindia.com": ("DNA", "Mumbai"),
    "thehansindia.com": ("The Hans India", "Hyderabad"),
    "thestatesman.com": ("The Statesman", "Kolkata"),
    "telegraphindia.com": ("The Telegraph", "Kolkata"),
    "outlookindia.com": ("Outlook", "New Delhi"),
    "freepressjournal.in": ("The Free Press Journal", "Mumbai"),
    "koimoi.com": ("Koimoi", "Mumbai"),
    "91mobiles.com": ("91mobiles", ""),
    "opindia.com": ("OpIndia", ""),
    "espn.in": ("ESPN India", ""),
    "vogue.in": ("Vogue India", "Mumbai"),
}

RIGHTS = ("Headline and link only, as collected in August 2020; the article text is not stored. "
          "Copyright remains with the publisher.")


def outlet_for(domain: str) -> tuple[str, str] | None:
    """(name, city) for an Indian outlet, or None. Unlisted .in domains count as Indian."""
    domain = domain.lower().removeprefix("www.").removeprefix("m.")
    best = None
    for key, val in INDIAN_OUTLETS.items():
        if (domain == key or domain.endswith("." + key)) and (best is None or len(key) > len(best[0])):
            best = (key, val)
    if best:
        return best[1]
    if domain.endswith(".in") or domain.endswith(".co.in"):
        return (domain, "")
    return None


def _read_records(path: str | Path) -> list[dict]:
    path = Path(path)
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith(".json") and not n.startswith("__MACOSX"))
            return json.loads(z.read(name))
    return json.loads(path.read_text())


def fetch(path: str | Path, collection: str = "", india_only: bool = True) -> Iterator[Page]:
    seen: set[str] = set()
    for r in _read_records(path):
        title, link = (r.get("title") or "").strip(), r.get("link") or ""
        if not title or not link or link in seen:
            continue
        outlet = outlet_for(r.get("domain", ""))
        if india_only and not outlet:
            continue
        seen.add(link)
        name, city = outlet or (r.get("domain", ""), "")
        yield Page(
            id="headline:" + hashlib.sha1(link.encode()).hexdigest()[:16],
            source="headline",
            newspaper=name,
            place=city,
            date=(r.get("published_date") or "")[:10],
            url=link,
            text=title,
            language=r.get("lang", "en"),
            ocr_engine="born-digital (no OCR)",
            rights=RIGHTS,
            collection=collection,
            section=(r.get("topic") or "").title(),
        )
