import json
import shutil
import subprocess
from pathlib import Path

import pytest

from timecapsule.models import Chunk
from timecapsule.rag import ResearchAssistant
from timecapsule.retrieval import Filters, Retriever
from timecapsule.retrieval.bm25 import BM25Index
from timecapsule.retrieval.text import stem, tokenize, variants

ROOT = Path(__file__).resolve().parents[1]

DOCS = [
    "The Titanic struck an iceberg and sank. The Carpathia picked up the survivors.",
    "Tho Tltanic disaster: survivors reach New York on the Carpathia tonight.",
    "A reward of fifty thousand dollars is offered. Reward notices were posted.",
    "Reward offered for the capture of the assassin. The reward is large.",
    "Secretary Seward was attacked in his bed but survived the assault.",
    "Influenza closes the schools and theatres; the health board orders masks.",
    "White Star officials say the Titanic carried twenty lifeboats.",
    "Senate committee to investigate the loss of the Titanic.",
    "Titanic memorial fund opened by the mayor.",
]


def _chunk(i, text, paper="Paper", date="1912-04-16", col="titanic", q=0.9):
    return Chunk(id=f"p{i}#0", page_id=f"p{i}", text=text, source="loc", newspaper=paper, date=date,
                 url=f"u{i}", collection=col, quality=q)


def test_tokenize_folds_long_s_and_stems_plurals_only():
    assert tokenize("The Preſident's survivors, Wilson") == ["president", "survivor", "wilson"]
    assert stem("bodies") == "body" and stem("glass") == "glass" and stem("status") == "status"


def test_variants_cover_ocr_confusions():
    v = variants("titanic")
    assert "tltanic" in v and "titanlc" in v
    assert "carpatlia" not in variants("seward")
    assert "rnasks" in variants("masks")  # m -> rn even for short words


def test_expansion_matches_misreadings_but_not_real_words():
    idx = BM25Index(DOCS)
    terms = {t.term: t.weight for t in idx.expand("Titanic Seward")}
    assert terms["titanic"] == 1.0
    assert terms.get("tltanic") == 0.5  # OCR misreading present in the corpus
    assert "reward" not in terms  # a common real word, not a misreading of "Seward"


def test_bm25_finds_garbled_passages():
    idx = BM25Index(DOCS)
    ranked = [d for d, _ in idx.search("Titanic Carpathia survivors")]
    assert {0, 1} <= set(ranked[:3])


def test_filters_and_diversity():
    chunks = [_chunk(i, f"Titanic news item number {i} about the Titanic.", paper="Big Daily") for i in range(6)]
    chunks.append(_chunk(9, "Titanic report from a small town weekly.", paper="Small Weekly", date="1912-04-20"))
    r = Retriever(chunks)
    hits = r.search("titanic", k=5, per_paper=4)
    assert sum(h.chunk.newspaper == "Big Daily" for h in hits[:4]) <= 4
    assert any(h.chunk.newspaper == "Small Weekly" for h in hits)
    only_late = r.search("titanic", filters=Filters(start="1912-04-19"))
    assert [h.chunk.newspaper for h in only_late] == ["Small Weekly"]


def test_extractive_answer_quotes_and_cites():
    chunks = [_chunk(i, t) for i, t in enumerate(DOCS)]
    ra = ResearchAssistant(chunks, [{"id": "titanic", "title": "Titanic", "context": "ctx"}])
    ans = ra.ask("Which ship picked up the Titanic survivors?", k=3)
    assert ans.evidence[0].quote in chunks[0].text or ans.evidence[0].quote in chunks[1].text
    assert "Carpathia" in ans.evidence[0].quote
    assert ans.collection["id"] == "titanic"
    assert ans.coverage["passages"] == len(ans.hits)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_browser_engine_matches_python(tmp_path):
    """site/assets/search.js must tokenize, expand and rank exactly like Python."""
    mod = tmp_path / "search.mjs"
    mod.write_text((ROOT / "site/assets/search.js").read_text())
    queries = ["Titanic Carpathia survivors", "Seward assault", "influenza masks", "reward assassin",
               "How did papers first report the Titanic?", "reported"]
    script = f"""
      import {{ Archive, tokenize }} from {json.dumps(str(mod))};
      const a = new Archive();
      a.addShard("c", {{ pages: {json.dumps([{"id": f"p{i}", "paper": f"P{i}"} for i in range(len(DOCS))])},
                         chunks: {json.dumps([[i, t, None, 1.0] for i, t in enumerate(DOCS)])} }});
      const out = {{}};
      for (const q of {json.dumps(queries)}) {{
        out[q] = {{
          terms: a.expand(q).map(t => [t.term, t.weight]),
          ranked: a.search(q, {{ k: 10, perPage: 9, perPaper: 9 }}).hits.map(h => [h.chunk.id, +h.score.toFixed(6)]),
        }};
      }}
      out.tokens = {json.dumps(DOCS)}.map(tokenize);
      console.log(JSON.stringify(out));
    """
    js = json.loads(subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True,
                                   text=True, check=True).stdout)
    idx = BM25Index(DOCS)
    assert js["tokens"] == [tokenize(d) for d in DOCS]
    for q in queries:
        assert js[q]["terms"] == [[t.term, t.weight] for t in idx.expand(q)]
        assert js[q]["ranked"] == [[d, round(s, 6)] for d, s in idx.search(q)]
