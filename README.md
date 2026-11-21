# The Time Capsule

**A lightweight, citation-first RAG system for research in historical newspapers.**

The Time Capsule turns OCR'd newspaper scans into a research tool. Ask a question in plain language and get
back the newspapers' own words: the best-matching sentence from each relevant passage, ordered in time, with
the newspaper, place, date and page for each, a link to the original scan, and the exact printed region of the page.
Nothing is generated unless you ask for it, and generated summaries must cite those same passages.

- **Website (GitHub Pages):** `https://ero2203.github.io/Time-Capsule-A-News-Archive/`, a static reading room
  that searches the whole archive in your browser. Nothing you type leaves your machine.
- **Python toolkit:** harvest sources, OCR your own scans, rebuild the archive, and ask questions from the
  command line, optionally with written answers from Claude.

The archive holds **191 scanned pages and issues from 126 newspapers in 105 places, printed 1865-1929**,
across 12 historical collections, plus an **India desk** built from this project's own archive: **7,648 headlines
from 87 Indian news outlets** (August 2020) and the **bilingual Hindi/English Gazette of India** of 30 September 2000.
The India desk also samples two centuries of Indian newspapers and gazettes (below).

## Sources

| Source | What it is | OCR | Citation level | Rights |
|---|---|---|---|---|
| [Chronicling America](https://www.loc.gov/collections/chronicling-america/) | Library of Congress & NEH National Digital Newspaper Program: US newspapers 1756-1963 | ALTO XML from NDNP partners (word boxes + confidence) | Page and printed region (IIIF crop) | No known restrictions |
| [Internet Archive Newspapers](https://archive.org/details/newspapers) | Over a million digitized issues worldwide | Internet Archive OCR (Tesseract) | Issue (deep link to in-scan search) | Pre-1931, US public domain; check item terms |
| Indian news headlines (project archive) | 7,648 headlines from 87 Indian outlets (Times of India, Indian Express, NDTV, The Hindu, Mint, ...), Aug 2020, from `legacy/Source Provider.zip` | Born-digital | Outlet, date, link to the article | Headline + link only; article text not stored |
| [The Gazette of India](https://archive.org/details/gazetteofindia) | Government of India's official journal; the 30 Sep 2000 issue (Part III, Sec. 4) the original scraper targeted | Internet Archive OCR (Google Cloud Vision), Hindi + English | Issue | Government publication, digitized by Public.Resource.Org |
| Your own scans | Any page images you have rights to | Tesseract via `timecapsule ocr` | Whatever your sidecar metadata provides | Yours |

The historical collections include only pages published before 1931. The [Sources page](site/sources.html) documents each source,
how it is accessed, and other open archives to explore (Trove, Papers Past, Delpher, Europeana Newspapers,
Gallica, CDNC, American Stories).

## Collections

The archive is organized as research collections, one per event, each with a date window, curated historical
context, reading notes on how the event was (mis)reported, and starter questions
(`corpus/collections.json`):

| Collection | Window |
|---|---|
| The Assassination of Abraham Lincoln | Apr 15-30, 1865 |
| The Great Chicago Fire | Oct 9-31, 1871 |
| The Johnstown Flood | Jun 1-20, 1889 |
| The Wright Brothers' First Flights | Dec 17, 1903 - Jan 31, 1904 |
| The 1906 San Francisco Earthquake and Fire | Apr 18 - May 5, 1906 |
| The Sinking of the Titanic | Apr 15-30, 1912 |
| The Sinking of the Lusitania | May 7-25, 1915 |
| The 1918 Influenza Pandemic | Oct 1918 |
| The Armistice of November 1918 (including the "false armistice") | Nov 7-16, 1918 |
| Ratification of the 19th Amendment | Aug 18-31, 1920 |
| Lindbergh's Transatlantic Flight | May 20 - Jun 15, 1927 |
| The Stock Market Crash of 1929 | Oct 24 - Nov 15, 1929 |
| **India desk:** Indian Headlines, August 2020 | Aug 1-18, 2020 |
| **India desk:** The Gazette of India, 30 September 2000 | Sep 30, 2000 |

| **India desk:** Bombay's English Press, 1811-1930 (decade sample of 4 papers) | 1811-1930 |
| **India desk:** Indian-Language Press: Tamil and Telugu, 1850-1930 | 1850-1930 |
| **India desk:** Gazettes of India Through Time (union and state) | 1920s-2020s |

### India archive: all of India's gazettes and newspapers on the Internet Archive

`site/india.html` catalogues **933,000+ items** by year and searches all of them in full text, live, through
the Internet Archive's search service (in English or Indian scripts):

- **Gazettes:** all 877,370 issues of the `gazetteofindia` collection in ~40 series (Gazette of India weekly and
  extraordinary, Haryana, Kerala, Rajasthan, Odisha, Bihar, Andhra Pradesh, Maharashtra, Karnataka, Tamil Nadu,
  Goa, Travancore, Fort St. George and more), plus 1,631 bound volumes from the Digital Library of India.
- **Newspapers:** Bombay Courier (1811-1842), The Bombay Gazette (1814-1914), The Bombay Guardian (1851-1889),
  The Bombay Chronicle (1913-1958), Tamil newspapers and periodicals (Endangered Archives Programme), Zamin Ryot
  (Telugu), Indian Opinion, Faridabad Majdoor Samachar, and recent e-paper editions (links only).

Public-domain material (newspapers before 1931, government gazettes) is sampled decade by decade into the corpus
above; later newspapers are catalogued and linked, never copied.

```bash
timecapsule india-search "plague" --scope bombay-papers --from 1896 --to 1900
timecapsule india-search "सेवानिवृत्ति" --scope gazettes
timecapsule india-catalog          # rebuild site/data/india-catalog.json from the Internet Archive
```

Search works in **Hindi and other Indian scripts** as well as English: the tokenizer keeps Devanagari, Bengali,
Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam and Urdu text (with vowel signs intact), sentence
splitting understands the danda (।), and OCR quality scoring is script-aware.

```bash
timecapsule ask "सेवानिवृत्ति के पश्चात् निजी क्षेत्र में नियोजन" --collection gazette-of-india-2000
timecapsule ask "Kozhikode plane crash" --collection india-headlines-2020
```

## How it works

```
 harvest            OCR                 clean               chunk                 retrieve                 answer
 loc.gov API   ->   ALTO XML      ->    rejoin hyphens  ->  ~150-word passages -> BM25 + OCR-misreading -> verbatim quotes, timeline,
 archive.org        IA OCR text         long s, noise       along printed         expansion + quality      context, coverage;
 your scans         Tesseract           quality score       blocks (keep bbox)    prior + diversity        optional cited Claude summary
```

- **OCR-aware retrieval.** Old newsprint OCR turns "Titanic" into "Tltanic" and "Carpathia" into "Carpatlia".
  Each query word is expanded to the OCR misreadings (rn/m, li/h, cl/d, e/c, single-letter slips) that actually occur
  in the archive and are much rarer than the word itself, so real words like "reward" are not mistaken for
  "Seward". Variants count for half.
- **Quality prior.** Every passage gets a 0-1 OCR quality score; noisy passages rank lower and are flagged, never hidden.
- **Region-level citations.** ALTO word coordinates give each Chronicling America passage a box on the page, so the
  site can show the exact printed region from the Library of Congress IIIF image server.
- **Diversity.** At most two passages per page and four per newspaper in the top results, so one big daily
  cannot drown out small-town weeklies.
- **Same engine everywhere.** `site/assets/search.js` mirrors `timecapsule/retrieval/`; a test runs both on the
  same data and requires identical rankings.
- **Optional dense retrieval** (`--dense`): a small sentence-embedding model fused with BM25 by reciprocal-rank fusion.

## Quick start

```bash
git clone https://github.com/ERo2203/Time-Capsule-A-News-Archive
cd Time-Capsule-A-News-Archive
pip install -e .
```

Ask a question (the harvested corpus ships in `data/corpus/`):

```bash
timecapsule ask "How far did newspapers say the flying machine flew?" --collection wright-brothers
```

```
[3] Yorkville enquirer, Yorkville, S.C., 1904-01-08, p. 2  (OCR quality 0.97)
    "Only those who are acquainted with practical aeronautics can appreciate the difficulties in
    attempting the first trials of a flying machine in a 25-mile gale."
    https://www.loc.gov/resource/sn84026925/1904-01-08/ed-1/?sp=2
    scan: https://tile.loc.gov/image-services/iiif/service:ndnp:scu:.../pct:16.42,5.28,16.64,9.69/pct:50/0/default.jpg
...
```

Useful options: `--from 1912-04-15 --to 1912-04-17`, `--source loc ia`, `--min-quality 0.8`, `-k 15`, `--json`.

Browse the website locally:

```bash
python -m http.server -d site 8000   # then open http://localhost:8000
```

### Written answers with Claude (optional)

```bash
pip install -e ".[llm]"
export ANTHROPIC_API_KEY=...
timecapsule ask "How did the first reports of the Titanic disaster differ from later ones?" --collection titanic --claude
```

Claude receives only the numbered passages and is instructed to cite every claim, report what the papers *said*
rather than what happened, point out where sources disagree, and keep historical background in a separate,
labelled section. The quoted evidence is always printed underneath so every claim can be checked.

### Grow the archive

```bash
# More pages for one collection (Chronicling America pages and Internet Archive issues)
timecapsule harvest --only titanic --loc-pages 40 --ia-issues 8 --force

# Add a new event: append an entry to corpus/collections.json, then
timecapsule harvest --only my-new-event

# Collections can also point at a headline file ("headlines_file") or at specific
# Internet Archive items ("ia_items"), e.g. more Gazette of India issues from
# https://archive.org/details/gazetteofindia

# OCR your own scans (needs the tesseract binary)
pip install -e ".[ocr]"
timecapsule ocr ~/scans/bombay-chronicle-1919 --collection my-collection

# Re-chunk everything and regenerate the website data
timecapsule build
```

Each scan can have a sidecar JSON with its citation (`newspaper`, `place`, `date`, `page`, `url`, `rights`);
see `timecapsule/sources/local_scans.py`.

A small JSON API is also available: `pip install -e ".[serve]" && timecapsule serve`, then `POST /api/ask`
with `{"question": "...", "collections": ["titanic"]}`.

## Repository layout

```
timecapsule/            Python package
  sources/              loc.py (Chronicling America), internet_archive.py, local_scans.py, polite cached HTTP
  ocr/                  alto.py (ALTO parser), clean.py (post-correction + quality), tesseract.py
  chunking.py           region-aware passages
  retrieval/            text.py (tokenizer, OCR variants), bm25.py, dense.py, hybrid search + diversity
  rag.py                extractive evidence briefs, Claude answers
  harvest.py build.py cli.py
corpus/collections.json research collections: date windows, queries, context, reading notes, questions
data/corpus/            harvested pages and passages (gzip'd JSON Lines)
site/                   GitHub Pages site (static HTML/CSS/JS + site/data shards)
tests/                  unit tests, including the browser/Python parity test
legacy/                 the original prototype; its headline dataset feeds the India desk
```

## Publishing the site

The workflow in `.github/workflows/pages.yml` deploys `site/` on every push to `main` that changes it. Enable it
once under **Settings → Pages → Build and deployment → Source: GitHub Actions**.

## Limitations

- The archive is a curated sample of a few hundred pages and issues per run, not a complete record. For
  exhaustive work, search the source archives directly. Absence here is not evidence of absence.
- Internet Archive passages are cited to the issue, not the page.
- The OCR quality score is a ranking heuristic, not a measured character accuracy.
- Newspapers reported what was believed on the day, often wrongly, and reflect the biases and language of their
  time. Read the [reading guide](site/method.html#reading).

## Acknowledgements

Page images and OCR: Library of Congress, Chronicling America (with the National Endowment for the Humanities
and state partners), and the Internet Archive. Collection context notes were written for this project; corrections
are welcome as issues.
