"""Cut OCR pages into citable passages.

Pages with layout (ALTO / Tesseract blocks) are chunked along the printed
regions, so each passage maps back to a box on the scan. Plain-text pages are
cut into overlapping word windows that try to end on a sentence.
"""

from __future__ import annotations

import re

from .models import Block, Chunk, Page
from .ocr.clean import clean_ocr_text, quality_score

MIN_WORDS = 15
TARGET_WORDS = 150
OVERLAP_WORDS = 30


def _union(a, b):
    if not a:
        return b
    if not b:
        return a
    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
    return (round(x0, 2), round(y0, 2), round(x1 - x0, 2), round(y1 - y0, 2))


def _same_column(a, b) -> bool:
    return bool(a and b) and abs(a[0] - b[0]) < 3 and abs((a[0] + a[2]) - (b[0] + b[2])) < 4


def _merge_small_blocks(blocks: list[Block]) -> list[Block]:
    """Join headline-sized blocks onto the next block in the same column."""
    out: list[Block] = []
    pending: Block | None = None
    for b in blocks:
        if pending is not None:
            if _same_column(pending.bbox, b.bbox) or not (pending.bbox and b.bbox):
                confs = [c for c in (pending.confidence, b.confidence) if c is not None]
                b = Block(
                    text=pending.text + "\n" + b.text,
                    bbox=_union(pending.bbox, b.bbox),
                    confidence=round(sum(confs) / len(confs), 3) if confs else None,
                )
            else:
                out.append(pending)
            pending = None
        if len(b.text.split()) < MIN_WORDS * 2:
            pending = b
        else:
            out.append(b)
    if pending is not None:
        out.append(pending)
    return out


def _windows(text: str) -> list[str]:
    words = text.split()
    if len(words) <= TARGET_WORDS:
        return [text]
    out, i = [], 0
    while i < len(words):
        end = min(len(words), i + TARGET_WORDS)
        # extend up to 40 words to finish the sentence
        for j in range(end, min(len(words), end + 40)):
            if re.search(r"[.!?\u0964][\"']?$", words[j - 1]):
                end = j
                break
        out.append(" ".join(words[i:end]))
        if end >= len(words):
            break
        i = max(end - OVERLAP_WORDS, i + 1)
    return out


def chunk_page(page: Page) -> list[Chunk]:
    pieces: list[tuple[str, tuple | None, float | None]] = []
    if page.source == "headline":
        # born-digital headline: one short passage, no OCR to clean or score
        return [Chunk(
            id=f"{page.id}#0", page_id=page.id, text=page.text, source=page.source,
            newspaper=page.newspaper, date=page.date, url=page.url, place=page.place,
            collection=page.collection, section=page.section, quality=1.0,
        )]
    if page.blocks:
        for b in _merge_small_blocks(page.blocks):
            pieces.append((clean_ocr_text(b.text), b.bbox, b.confidence))
    else:
        for w in _windows(clean_ocr_text(page.text).replace("\n", " ")):
            pieces.append((w, None, page.ocr_confidence))

    chunks = []
    for text, bbox, conf in pieces:
        if len(text.split()) < MIN_WORDS:
            continue
        chunks.append(Chunk(
            id=f"{page.id}#{len(chunks)}",
            page_id=page.id,
            text=text,
            source=page.source,
            newspaper=page.newspaper,
            date=page.date,
            url=page.url,
            place=page.place,
            page=page.page,
            collection=page.collection,
            section=page.section,
            bbox=bbox,
            iiif=page.iiif,
            ocr_confidence=conf,
            quality=quality_score(text),
        ))
    return chunks
