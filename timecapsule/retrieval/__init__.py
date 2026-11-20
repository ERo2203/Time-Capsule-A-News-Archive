"""Hybrid retrieval over newspaper passages: BM25 (+ optional dense), filters, diversity."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..models import Chunk
from .bm25 import BM25Index


@dataclass
class Filters:
    start: str | None = None  # ISO date, inclusive
    end: str | None = None
    collections: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    min_quality: float = 0.0

    def allows(self, c: Chunk) -> bool:
        if self.start and c.date and c.date < self.start:
            return False
        if self.end and c.date and c.date > self.end:
            return False
        if self.collections and c.collection not in self.collections:
            return False
        if self.sources and c.source not in self.sources:
            return False
        return c.quality >= self.min_quality


@dataclass
class Hit:
    chunk: Chunk
    score: float


class Retriever:
    def __init__(self, chunks: list[Chunk], dense: bool = False, cache_dir: Path | None = None):
        self.chunks = chunks
        texts = [c.text for c in chunks]
        self.bm25 = BM25Index(texts, [c.quality for c in chunks])
        self.dense = None
        if dense:
            from .dense import DenseIndex

            self.dense = DenseIndex(texts, cache_dir or Path("data/corpus"))

    def search(self, query: str, k: int = 10, filters: Filters | None = None,
               per_page: int = 2, per_paper: int = 4) -> list[Hit]:
        filters = filters or Filters()
        allowed = {i for i, c in enumerate(self.chunks) if filters.allows(c)}
        lexical = self.bm25.search(query, k=200, allowed=allowed)
        if self.dense:
            ranked = _rrf([lexical, self.dense.search(query, k=200, allowed=allowed)])
        else:
            ranked = lexical
        return _diversify([Hit(self.chunks[i], s) for i, s in ranked], k, per_page, per_paper)


def _rrf(rankings: list[list[tuple[int, float]]], k: int = 60) -> list[tuple[int, float]]:
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, (doc, _) in enumerate(ranking):
            fused[doc] = fused.get(doc, 0.0) + 1.0 / (k + rank + 1)
    return sorted(fused.items(), key=lambda x: -x[1])


def _diversify(hits: list[Hit], k: int, per_page: int, per_paper: int) -> list[Hit]:
    """Cap passages per page and per newspaper so one paper can't drown out the rest."""
    pages: Counter[str] = Counter()
    papers: Counter[str] = Counter()
    out, overflow = [], []
    for h in hits:
        if pages[h.chunk.page_id] >= per_page or papers[h.chunk.newspaper] >= per_paper:
            overflow.append(h)
            continue
        pages[h.chunk.page_id] += 1
        papers[h.chunk.newspaper] += 1
        out.append(h)
        if len(out) == k:
            return out
    return (out + overflow)[:k]
