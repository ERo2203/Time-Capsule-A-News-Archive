"""BM25 with OCR-tolerant query expansion and an OCR-quality prior.

Why lexical first: historical questions are full of names, places and dates
("Carpathia", "Johnstown", "Colby"), which exact-term ranking handles better
than small embedding models do. OCR damage is handled at query time: each query
word is expanded to the misspellings an OCR engine is likely to have produced
that actually occur in the corpus, weighted below the exact word.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from .text import query_tokens, stem, tokenize, variants

EXPANSION_WEIGHT = 0.5
MAX_EXPANSIONS = 6
# A misreading is rarer than the word it garbles. Variants at least this
# fraction as common as the query word are probably real words ("reward" for
# "Seward") and are not used.
MAX_VARIANT_DF_RATIO = 0.34


@dataclass
class QueryTerm:
    term: str
    weight: float
    origin: str  # the query word it came from


class BM25Index:
    def __init__(self, docs: list[str], qualities: list[float] | None = None, k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.lengths: list[int] = []
        for i, text in enumerate(docs):
            toks = tokenize(text)
            self.lengths.append(len(toks))
            for t, tf in Counter(toks).items():
                self.postings[t].append((i, tf))
        self.n = len(docs)
        self.avgdl = (sum(self.lengths) / self.n) if self.n else 0.0
        self.qualities = qualities or [1.0] * self.n

    def idf(self, term: str) -> float:
        df = len(self.postings.get(term, ()))
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5)) if df else 0.0

    def expand(self, query: str, fuzzy: bool = True) -> list[QueryTerm]:
        terms: dict[str, QueryTerm] = {}
        for raw in query_tokens(query):
            t = stem(raw)
            terms[t] = QueryTerm(t, 1.0, raw)
            if not fuzzy or len(raw) < 5 or raw.isdigit():
                continue
            df_t = len(self.postings.get(t, ()))
            cands = []
            for v in variants(raw):
                sv = stem(v)
                if sv == t or sv in terms or sv not in self.postings:
                    continue
                df_v = len(self.postings[sv])
                if df_t and df_v >= MAX_VARIANT_DF_RATIO * df_t:
                    continue
                cands.append((df_v, sv))
            for _, sv in sorted(cands, reverse=True)[:MAX_EXPANSIONS]:
                terms[sv] = QueryTerm(sv, EXPANSION_WEIGHT, raw)
        return list(terms.values())

    def search(self, query: str, k: int = 50, allowed: set[int] | None = None,
               fuzzy: bool = True) -> list[tuple[int, float]]:
        scores: dict[int, float] = defaultdict(float)
        matched: dict[int, set[str]] = defaultdict(set)
        qterms = self.expand(query, fuzzy)
        n_origins = len({q.origin for q in qterms}) or 1
        for q in qterms:
            idf = self.idf(q.term)
            for doc, tf in self.postings.get(q.term, ()):
                if allowed is not None and doc not in allowed:
                    continue
                dl = self.lengths[doc]
                denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                scores[doc] += q.weight * idf * tf * (self.k1 + 1) / denom
                matched[doc].add(q.origin)
        ranked = []
        for doc, s in scores.items():
            coverage = len(matched[doc]) / n_origins  # reward passages that match more of the question
            prior = 0.6 + 0.4 * self.qualities[doc]  # garbled OCR ranks lower, never disappears
            ranked.append((doc, s * (0.5 + 0.5 * coverage) * prior))
        ranked.sort(key=lambda x: -x[1])
        return ranked[:k]
