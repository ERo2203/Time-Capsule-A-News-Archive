"""India archive: every Indian gazette and newspaper we can find on the
Internet Archive, catalogued, searchable live, and sampled into the corpus.

Three layers, because "all of it" is far too large to copy:

1. **Catalog** (``build_catalog``): each source below, and every gazette series
   in the 877,000-item ``gazetteofindia`` collection, with issue counts per year
   and links. Small enough to ship with the website.
2. **Live search** (``live_search``): the Internet Archive's full-text search,
   scoped to these sources, from the command line or the browser.
3. **Full-text sample** (``sample_issues``): a few issues per decade from each
   historical source, harvested into the corpus like any other collection, so
   they get the same OCR cleanup, ranking and citations.

Rights tiers: ``full`` sources are public domain (newspapers published before
1931, and government gazettes, which are official legal texts); their OCR text
may be copied into the corpus. ``link`` sources (recent newspapers) are only
catalogued and linked; their text is never copied.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterator

from .models import Page
from .sources.http import get
from .sources.internet_archive import issue_text, metadata

FTS_URL = "https://archive.org/services/search/beta/page_production/"
SCRAPE_URL = "https://archive.org/services/search/v1/scrape"
PD_NEWSPAPER_CUTOFF = 1930  # newspapers published before 1931 are public domain in the US

# Each source: an Internet Archive query plus the facts a researcher needs.
SOURCES: list[dict] = [
    {"id": "bombay-courier", "sampled": True, "group": "Newspapers: English, colonial era", "name": "Bombay Courier",
     "place": "Bombay", "language": "English", "rights": "full",
     "query": 'collection:IndiaHistory AND title:"Bombay Courier"',
     "note": "One of Bombay's earliest English newspapers, carrying government notices, shipping news and advertisements."},
    {"id": "bombay-gazette", "sampled": True, "group": "Newspapers: English, colonial era", "name": "The Bombay Gazette",
     "place": "Bombay", "language": "English", "rights": "full",
     "query": 'collection:IndiaHistory AND title:"Bombay Gazette"',
     "note": "Long-running Bombay daily, the largest run here: a century of commerce, politics, plague years and the city's growth."},
    {"id": "bombay-guardian", "sampled": True, "group": "Newspapers: English, colonial era", "name": "The Bombay Guardian",
     "place": "Bombay", "language": "English", "rights": "full",
     "query": 'collection:IndiaHistory AND title:"Bombay Guardian"',
     "note": "A Christian missionary weekly; reads Bombay life through a religious and reformist lens."},
    {"id": "bombay-chronicle", "sampled": True, "group": "Newspapers: English, colonial era", "name": "The Bombay Chronicle",
     "place": "Bombay", "language": "English", "rights": "full",
     "query": 'collection:IndiaHistory AND title:"Bombay Chronicle"',
     "note": "Nationalist daily founded by Pherozeshah Mehta in 1910; central to coverage of the freedom movement. "
             "Issues from 1931 on are catalogued and searchable live but not copied, as they may still be in copyright."},
    {"id": "hindoo-patriot", "group": "Newspapers: English, colonial era", "name": "The Hindoo Patriot",
     "place": "Calcutta", "language": "English", "rights": "full", "sampled": True,
     "query": 'collection:IndiaHistory AND title:"Hindoo Patriot"',
     "note": "Calcutta weekly founded in 1853. Under Harish Chandra Mukherjee it took up the cause of the indigo "
             "cultivators, and under Kristo Das Pal it spoke for the Bengali landed and educated classes."},
    {"id": "calcutta-journal", "group": "Newspapers: English, colonial era",
     "name": "The Calcutta Journal, or Political, Commercial and Literary Gazette", "place": "Calcutta",
     "language": "English", "rights": "full", "sampled": True,
     "query": "collection:pub_calcutta-journal-political-commercial-literary-gazette",
     "note": "Founded in 1818 by James Silk Buckingham, whose criticism of the East India Company's government led "
             "to his deportation in 1823: a landmark in the history of press freedom in India."},
    {"id": "indian-mirror", "group": "Newspapers: English, colonial era", "name": "The Indian Mirror",
     "place": "Calcutta", "language": "English", "rights": "full", "sampled": False,
     "query": 'collection:ColumbiaUniversityLibraries AND title:"Indian Mirror"',
     "note": "Calcutta paper associated with the Brahmo Samaj reform movement and one of the earliest English "
             "dailies run by Indians. Bound annual volumes (1870s), searchable live; too large to sample here."},
    {"id": "vernacular-reports", "group": "Newspapers: Indian languages, in translation",
     "name": "Selections from the Vernacular Newspapers (Indian Newspaper Reports)", "place": "British India",
     "language": "English translations of Indian-language papers", "rights": "full", "sampled": True,
     "query": "collection:(pub_indian_newspaper_reports OR pub_indian-newspaper-reports) AND NOT title:contents",
     "note": "Weekly reports in which government translators summarized and quoted what Indian-language newspapers "
             "in each province were saying. They preserve the views of hundreds of Hindi, Urdu, Bengali, Marathi, "
             "Gujarati, Tamil and other papers that do not survive in digitized form, read through official eyes."},
    {"id": "indian-opinion", "group": "Newspapers: English, colonial era", "name": "Indian Opinion",
     "place": "Durban (South Africa)", "language": "English, Gujarati", "rights": "link",
     "query": 'collection:HindSwaraj AND title:"Indian Opinion"',
     "note": "Founded by M. K. Gandhi in South Africa in 1903; the paper of his satyagraha campaigns. Bound volumes."},
    {"id": "tamil-periodicals", "sampled": True, "group": "Newspapers: Indian languages", "name": "Tamil newspapers and periodicals",
     "place": "Tamil Nadu and Sri Lanka", "language": "Tamil", "rights": "full",
     "query": "collection:(tamil-newspapers OR tamil-newsletters)",
     "note": "Digitized through the British Library's Endangered Archives Programme: Narpotakam (1850s on), "
             "Janavinotini, Arunotayam, Janacakti, Sivaji and many more."},
    {"id": "zamin-ryot", "sampled": True, "group": "Newspapers: Indian languages", "name": "Zamin Ryot", "place": "Nellore",
     "language": "Telugu", "rights": "full",
     "query": "collection:zamin-ryot",
     "note": "Telugu weekly from Nellore, published from 1930; its name refers to the ryots (cultivators) of zamindari estates."},
    {"id": "faridabad-majdoor-samachar", "group": "Newspapers: Indian languages", "name": "Faridabad Majdoor Samachar",
     "place": "Faridabad", "language": "Hindi", "rights": "link",
     "query": "collection:fms_newspaper",
     "note": "Workers' newspaper from the industrial belt of Faridabad, near Delhi."},
    {"id": "modern-epapers", "group": "Newspapers: recent e-paper editions (links only)",
     "name": "Recent Indian e-paper editions", "place": "India",
     "language": "English, Telugu, Kannada, Tamil", "rights": "link",
     "query": ("collection:(newspapers-telugu OR prajavani-newspaper OR mysuru-mithra-newspaper OR vishwavani-newspaper "
               "OR vijay-karnataka-newspaper OR star-of-mysore-newspaper OR the-new-indian-express OR the-hindu "
               "OR sdp-daily OR the-times-of-india-newspaper)"),
     "note": "Recent editions of The Hindu, The New Indian Express, The Times of India, Prajavani, Andhra Bhoomi, "
             "Star of Mysore and others, uploaded by Archive users. In copyright: catalogued and linked only."},
    {"id": "dli-gazettes", "sampled": False, "group": "Gazettes", "name": "Historical gazette volumes (Digital Library of India)",
     "place": "India", "language": "English and others", "rights": "full",
     "query": "collection:digitallibraryindia AND title:gazette",
     "note": "Bound gazette volumes from provincial and princely-state governments, scanned by the Digital Library of India."},
]

GAZETTE_QUERY = "collection:gazetteofindia"

# Live-search scopes offered on the site and the CLI (recent e-papers are left out).
SCOPES: dict[str, str] = {
    "all": "(collection:gazetteofindia OR collection:IndiaHistory OR collection:tamil-newspapers "
           "OR collection:tamil-newsletters OR collection:zamin-ryot "
           "OR collection:pub_calcutta-journal-political-commercial-literary-gazette "
           "OR collection:pub_indian_newspaper_reports OR collection:pub_indian-newspaper-reports)",
    "gazettes": "collection:gazetteofindia",
    "bombay-papers": 'collection:IndiaHistory AND title:("Bombay Gazette" OR "Bombay Chronicle" OR "Bombay Courier" OR "Bombay Guardian")',
    "calcutta-papers": '(collection:IndiaHistory AND title:"Hindoo Patriot") OR '
                       'collection:pub_calcutta-journal-political-commercial-literary-gazette OR '
                       '(collection:ColumbiaUniversityLibraries AND title:"Indian Mirror")',
    "vernacular-reports": "collection:(pub_indian_newspaper_reports OR pub_indian-newspaper-reports)",
    "tamil": "collection:(tamil-newspapers OR tamil-newsletters)",
    "telugu": "collection:zamin-ryot",
}


def _scrape(query: str, fields: str) -> Iterator[dict]:
    cursor = None
    while True:
        params = {"q": query, "fields": fields, "count": 10000}
        if cursor:
            params["cursor"] = cursor
        data = json.loads(get(SCRAPE_URL, params=params, min_interval=1.0, timeout=300, cache=False))
        yield from data.get("items", [])
        cursor = data.get("cursor")
        if not cursor:
            return


def _year(item: dict) -> int | None:
    y = item.get("year")
    if isinstance(y, list):
        y = y[0] if y else None
    try:
        return int(str(y)[:4]) if y else None
    except ValueError:
        return None


_SERIES_ALIASES = {"Chattisgarh": "Chhattisgarh", "Fort St. George": "Fort St. George (Madras)",
                   "Orissa": "Odisha"}
_STATE_FROM_ID = re.compile(r"^in\.gazette\.([a-z_]+?)(?:arch|_ordinary|_extraordinary)?\.", re.I)


def gazette_series(identifier: str, title: str) -> str:
    """Name the series an item belongs to (e.g. 'Gazette of India: Extraordinary', 'Haryana Gazette')."""
    t = title if isinstance(title, str) else (title or [""])[0]
    tl = t.lower()
    if tl.startswith("union government") or "gazette of india" in tl or identifier.startswith(("in.gazette.central", "in.gazette.e.", "in.gazette.csl", "in.gazette.19", "in.gazette.20")):
        if "extraordinary" in tl or ".e." in identifier:
            return "Gazette of India: Extraordinary"
        if "weekly" in tl or ".w." in identifier or "csl_weekly" in identifier:
            return "Gazette of India: Weekly"
        return "Gazette of India"
    name = re.split(r",|\s-\s|\(| No\.| Number", t, maxsplit=1)[0].strip()
    name = re.sub(r"\s+\d{4}.*$", "", name).strip()
    if not name or name[0].isdigit():
        m = _STATE_FROM_ID.match(identifier)
        name = m.group(1).replace("_", " ") if m else ""
    # one series per state: drop qualifiers so "Maharashtra" and "Maharashtra Gazette" merge
    base = re.sub(r"\b(the|of|government|gazette|ordinary|extra ?ordinary|daily|weekly|official)\b", " ", name, flags=re.I)
    base = " ".join(w if not w.islower() else w.title() for w in base.split())
    base = _SERIES_ALIASES.get(base, base)
    return f"{base} Gazette" if base else "Other gazettes"


def build_catalog(out: Path = Path("site/data/india-catalog.json"), gazette_items: Path | None = None) -> dict:
    """Count every source and gazette series by year. ``gazette_items`` may be a
    JSON-lines file of {identifier,title,year} records already scraped."""
    sources = []
    for s in SOURCES:
        years: Counter[int] = Counter()
        n = 0
        for item in _scrape(s["query"], "identifier,year"):
            n += 1
            if (y := _year(item)):
                years[y] += 1
        print(f"  {s['name']}: {n:,} items")
        sources.append({**s, "total": n, "years": dict(sorted(years.items()))})

    series_years: dict[str, Counter[int]] = defaultdict(Counter)
    series_total: Counter[str] = Counter()
    items = (json.loads(line) for line in open(gazette_items)) if gazette_items else _scrape(GAZETTE_QUERY, "identifier,title,year")
    for item in items:
        name = gazette_series(item.get("identifier", ""), item.get("title", ""))
        series_total[name] += 1
        if (y := _year(item)):
            series_years[name][y] += 1
    for name in [n for n, c in series_total.items() if c < 5 and n != "Other gazettes"]:
        # typos and test uploads: fold into one bucket
        series_total["Other gazettes"] += series_total.pop(name)
        series_years["Other gazettes"].update(series_years.pop(name, Counter()))
    gazettes = []
    for name, total in series_total.most_common():
        base = name.removesuffix(" Gazette").replace(" (Madras)", "")
        q = (f"collection:gazetteofindia AND title:({base})" if not name.startswith("Gazette of India")
             else "collection:gazetteofindia AND " + ('title:extraordinary' if 'Extraordinary' in name else
                                                       'title:weekly AND title:"gazette of india"' if 'Weekly' in name else
                                                       'title:"gazette of india"'))
        gazettes.append({"name": name, "total": total, "years": dict(sorted(series_years[name].items())), "query": q})
    print(f"  gazetteofindia: {sum(series_total.values()):,} items in {len(gazettes)} series")

    catalog = {"sources": sources, "gazettes": gazettes, "gazette_total": sum(series_total.values()),
               "scopes": SCOPES, "pd_newspaper_cutoff": PD_NEWSPAPER_CUTOFF}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")))
    return catalog


def live_search(query: str, scope: str = "all", start: int | None = None, end: int | None = None,
                hits: int = 20) -> tuple[int, list[dict]]:
    """Full-text search across the Internet Archive, scoped to Indian sources."""
    q = f"({query}) AND {SCOPES.get(scope, scope)}"
    if start or end:
        q += f" AND year:[{start or 1700} TO {end or 2100}]"
    params = {"user_query": q, "hits_per_page": hits, "service_backend": "fts"}
    data = json.loads(get(FTS_URL, params=params, min_interval=1.0, cache=False))
    body = data.get("response", {}).get("body", {}).get("hits", {})
    out = []
    for h in body.get("hits", []):
        f = h["fields"]
        snippet = " ... ".join(h.get("highlight", {}).get("text", []))
        out.append({
            "identifier": f["identifier"], "title": f.get("title", ""), "date": (f.get("date") or "")[:10],
            "page": f.get("page_num"), "snippet": re.sub(r"\s+", " ", snippet),
            "url": f"https://archive.org/details/{f['identifier']}?q={urllib.parse.quote(query)}",
        })
    return body.get("total", 0), out


def sample_issues(query: str, start: int, end: int, per_decade: int = 1, max_chars: int = 400_000,
                  candidates: int = 6, sort: str = "spread") -> list[str]:
    """Pick up to ``per_decade`` items per decade with usable OCR text no longer than ``max_chars``.

    ``sort="spread"`` (default) takes candidates at evenly spaced points through
    the decade in date order, so a sample is not bunched in its first months.
    ``sort="random"`` asks the Internet Archive for random items instead.
    """
    search = "https://archive.org/advancedsearch.php"
    chosen = []
    for decade in range(start // 10 * 10, end + 1, 10):
        lo, hi = max(decade, start), min(decade + 9, end)
        q = f"({query}) AND year:[{lo} TO {hi}]"
        if sort == "random":
            params = {"q": q, "fl[]": ["identifier"], "rows": candidates, "output": "json", "sort[]": "random"}
            idents = [d["identifier"] for d in json.loads(get(search, params=params, min_interval=1.0))["response"]["docs"]]
        else:
            count = json.loads(get(search, params={"q": q, "rows": 0, "output": "json"}, min_interval=1.0))["response"]["numFound"]
            k = min(count, candidates)
            idents = []
            for i in range(k):
                pos = 1 + (i * count) // k  # 1-based position in date order
                params = {"q": q, "fl[]": ["identifier"], "rows": 1, "page": pos, "output": "json",
                          "sort[]": ["date asc", "identifier asc"]}
                docs = json.loads(get(search, params=params, min_interval=0.5))["response"]["docs"]
                idents += [d["identifier"] for d in docs]
            # interleave so early picks come from across the whole decade
            step = max(1, len(idents) // max(1, per_decade))
            idents = [idents[j] for off in range(step) for j in range(off, len(idents), step)]
        got = 0
        for ident in idents:
            if got >= per_decade:
                break
            if ident in chosen:
                continue
            meta = metadata(ident)
            dj = next((f for f in meta.get("files", []) if f["name"].endswith("_djvu.txt")), None)
            size = int(dj.get("size") or 0) if dj else 0
            if not dj or size > max_chars or size < 3000:
                continue
            chosen.append(ident)
            got += 1
    return chosen


_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}


def _iso(date: str) -> str:
    """'1987-1-1T...' -> '1987-01-01'; 'December 10-December 15, 1875' -> '1875-12-10'."""
    m = re.match(r"(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", date or "")
    if not m:
        w = re.search(r"([A-Za-z]+)\s+(\d{1,2})\D.*?(\d{4})", date or "")
        if w and w.group(1).lower() in _MONTHS:
            return f"{w.group(3)}-{_MONTHS[w.group(1).lower()]:02d}-{int(w.group(2)):02d}"
        y = re.search(r"\b(1[6-9]\d\d|20\d\d)\b", date or "")
        return y.group(1) if y else ""
    y, mo, d = m.group(1), m.group(2), m.group(3)
    return "-".join([y] + [x.zfill(2) for x in (mo, d) if x])


def fetch_sample(source: dict, start: int, end: int, collection: str, per_decade: int = 1,
                 max_chars: int = 400_000, kind: str = "ia", sort: str = "identifier asc",
                 candidates: int = 6) -> Iterator[Page]:
    """Harvest a decade-by-decade sample of one source into ``Page`` records."""
    for ident in sample_issues(source["query"], start, end, per_decade, max_chars, candidates, sort):
        meta = metadata(ident)
        md = meta.get("metadata", {})
        text = issue_text(ident, meta.get("files", []))
        if not text.strip():
            continue
        title = md.get("title", ident)
        title = title[0] if isinstance(title, list) else title
        langs = md.get("language", "")
        langs = "+".join(langs) if isinstance(langs, list) else langs
        name = source.get("name") if kind == "ia" else gazette_series(ident, title)
        if source["id"] == "vernacular-reports":  # cite each report by its own title (often names the province)
            name = re.sub(r"\s+\d{4}[-\s].*$|\s+[A-Z][a-z]+ \d{1,2}[-,].*$", "", title).strip() or name
        if source["id"] == "tamil-periodicals":
            name = re.sub(r"\s*\[.*$", "", title).strip('" ') or name
        yield Page(
            id=f"{kind}:{ident}", source=kind, newspaper=name, place=source.get("place", ""),
            date=_iso(md.get("date") or ""), url=f"https://archive.org/details/{ident}", text=text,
            language=langs or "en", ocr_engine=f"Internet Archive OCR ({md.get('ocr', 'unknown')})",
            rights="Public domain: published before 1931" if kind == "ia" else
                   "Official government gazette (public legal record), via Public.Resource.Org and the Internet Archive",
            collection=collection, section=title if kind == "gazette" else "",
        )
