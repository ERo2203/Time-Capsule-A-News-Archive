"""Retrieval-augmented answers for newspaper research.

Two answer modes share one retrieval step:

* ``extractive`` (default, no model, no API key): picks the sentences in the
  retrieved passages that best match the question, orders them by publication
  date, and reports coverage (how many papers, places and days). Every line is
  a verbatim quote with a citation, so nothing is invented.
* ``claude`` (optional): sends the numbered passages to Claude with
  instructions to answer only from them, cite every claim, flag OCR damage and
  contradictions, and keep era context separate from what the sources say.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from .models import Chunk
from .retrieval import Filters, Hit, Retriever
from .retrieval.text import tokenize

_SENT_SPLIT = re.compile(r"(?<=[.!?])[\"']?\s+(?=[\"'A-Z])")


@dataclass
class Evidence:
    n: int
    quote: str
    chunk: Chunk


@dataclass
class Answer:
    question: str
    hits: list[Hit]
    evidence: list[Evidence]
    coverage: dict
    collection: dict | None = None
    written: str | None = None  # LLM answer, when requested
    notes: list[str] = field(default_factory=list)


def _best_sentence(text: str, qterms: dict[str, float], max_words: int = 60) -> str:
    sents = [s.strip() for s in _SENT_SPLIT.split(text.replace("\n", " ")) if len(s.split()) >= 4]
    if not sents:
        return " ".join(text.split()[:max_words])
    best_i, best = 0, -1.0
    for i, s in enumerate(sents):
        toks = set(tokenize(s))
        score = sum(w for t, w in qterms.items() if t in toks) / math.sqrt(len(s.split()) + 5)
        if score > best:
            best_i, best = i, score
    quote = sents[best_i]
    # add the next sentence if the best one is short, for readable context
    if len(quote.split()) < 18 and best_i + 1 < len(sents):
        quote += " " + sents[best_i + 1]
    words = quote.split()
    return " ".join(words[:max_words]) + (" ..." if len(words) > max_words else "")


def coverage(hits: list[Hit]) -> dict:
    chunks = [h.chunk for h in hits]
    dates = sorted(c.date for c in chunks if c.date)
    return {
        "passages": len(chunks),
        "newspapers": len({c.newspaper for c in chunks}),
        "places": sorted({c.place for c in chunks if c.place}),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "sources": dict(Counter(c.source for c in chunks)),
        "mean_quality": round(sum(c.quality for c in chunks) / len(chunks), 2) if chunks else None,
    }


class ResearchAssistant:
    def __init__(self, chunks: list[Chunk], collections: list[dict] | None = None, dense: bool = False):
        self.retriever = Retriever(chunks, dense=dense)
        self.collections = {c["id"]: c for c in (collections or [])}

    def _collection_for(self, hits: list[Hit], filters: Filters) -> dict | None:
        if len(filters.collections) == 1:
            return self.collections.get(filters.collections[0])
        if not hits:
            return None
        cid, n = Counter(h.chunk.collection for h in hits).most_common(1)[0]
        return self.collections.get(cid) if n >= max(2, len(hits) // 2) else None

    def ask(self, question: str, k: int = 8, filters: Filters | None = None, mode: str = "extractive",
            model: str = "claude-opus-5-5") -> Answer:
        filters = filters or Filters()
        hits = self.retriever.search(question, k=k, filters=filters)
        bm25 = self.retriever.bm25
        qterms = {q.term: q.weight * bm25.idf(q.term) for q in bm25.expand(question)}
        evidence = [Evidence(i + 1, _best_sentence(h.chunk.text, qterms), h.chunk) for i, h in enumerate(hits)]
        ans = Answer(question, hits, evidence, coverage(hits), self._collection_for(hits, filters))
        low = [e.n for e in evidence if e.chunk.quality < 0.6]
        if low:
            ans.notes.append(f"OCR quality is poor in source(s) {', '.join(map(str, low))}; check the scan before quoting.")
        if not hits:
            ans.notes.append("No passages matched. Try other spellings, period terms, or a wider date range.")
        if mode == "claude" and hits:
            ans.written = write_with_claude(question, hits, ans.collection, model=model)
        return ans


SYSTEM_PROMPT = """You are a research assistant for historians working with digitized historical newspapers.
The sources you receive are passages of OCR text from scanned newspaper pages. They contain OCR errors
(misread letters, broken words, text from neighbouring columns run together) and they reflect the
language, assumptions and biases of their time.

How to answer:
- Answer only from the numbered sources. Put the source number in brackets, like [3], after every
  claim. If several sources agree, cite them together [2][5].
- Say what the newspapers reported, not what happened: "The Evening Star reported that ..." Newspapers
  were often wrong, especially in first reports. Point out where sources disagree, and how reports
  changed over the dates given.
- You may silently read through obvious OCR misspellings, but do not quote a garbled passage as if it
  were clean. If a key passage is too damaged to read with confidence, say so and suggest checking
  the scan.
- If the sources do not answer the question, say so plainly and suggest better search terms or dates.
- If collection background is provided, you may use it in a short final section headed
  "Historical context", kept clearly separate from what the sources say.
- Write in plain prose, a few short paragraphs, without markdown headings except "Historical context"."""


def _format_sources(hits: list[Hit]) -> str:
    parts = []
    for i, h in enumerate(hits, 1):
        c = h.chunk
        parts.append(
            f"[{i}] {c.citation()} (OCR quality {c.quality:.2f}; {c.url})\n\"\"\"\n{c.text}\n\"\"\""
        )
    return "\n\n".join(parts)


def write_with_claude(question: str, hits: list[Hit], collection: dict | None,
                      model: str = "claude-opus-5-5") -> str:
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover - optional extra
        raise SystemExit('Written answers need: pip install "timecapsule[llm]"') from e

    background = ""
    if collection:
        background = (f"\n\nCollection background ({collection['title']}):\n{collection['context']}\n"
                      f"Reading notes: {collection.get('reading_notes', '')}")
    user = f"Sources:\n\n{_format_sources(hits)}{background}\n\nQuestion: {question}"

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY or an `ant auth login` profile
    with client.beta.messages.stream(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # if a request is declined, the API retries it on a fallback model
        messages=[{"role": "user", "content": user}],
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason == "refusal":
        return "The model declined to answer this question. The quoted evidence above is unaffected."
    return "".join(b.text for b in message.content if b.type == "text").strip()
