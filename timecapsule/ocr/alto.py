"""Parse ALTO XML, the OCR format used by the Library of Congress and most
national newspaper programmes (NDNP, Europeana Newspapers, Delpher, Trove ...).

ALTO keeps what plain text throws away: the layout block each word belongs to,
its position on the page, and the OCR engine's word confidence (``WC``). We
keep all three so passages can be cited down to the region of the scan.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..models import Block
from .clean import normalize


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _box(el) -> tuple[float, float, float, float] | None:
    try:
        x, y = float(el.get("HPOS")), float(el.get("VPOS"))
        return x, y, x + float(el.get("WIDTH")), y + float(el.get("HEIGHT"))
    except (TypeError, ValueError):
        return None


def parse_alto(xml: bytes | str, max_words: int = 140) -> tuple[list[Block], float | None]:
    """Return (blocks, mean word confidence) for one ALTO page.

    Each ALTO ``TextBlock`` is split into passages of at most ``max_words``
    words on line boundaries, so a passage's box covers only the lines it came
    from. Words split by a line-end hyphen (``<HYP>``) are re-joined. Boxes are
    percentages of the printed page.
    """
    root = ET.fromstring(xml)
    page_w = page_h = None
    for el in root.iter():
        if _local(el.tag) == "Page":
            page_w = float(el.get("WIDTH") or 0) or None
            page_h = float(el.get("HEIGHT") or 0) or None
            break

    blocks: list[Block] = []
    tot_conf = 0.0
    tot_chars = 0

    def flush(lines, box, conf, chars):
        text = "\n".join(lines).strip()
        if not text:
            return
        bbox = None
        if page_w and page_h and box:
            x0, y0, x1, y1 = box
            bbox = (
                round(100 * x0 / page_w, 2), round(100 * y0 / page_h, 2),
                round(100 * (x1 - x0) / page_w, 2), round(100 * (y1 - y0) / page_h, 2),
            )
        blocks.append(Block(text=text, bbox=bbox, confidence=round(conf / chars, 3) if chars else None))

    for tb in root.iter():
        if _local(tb.tag) != "TextBlock":
            continue
        lines: list[str] = []
        box = None
        n_words = 0
        carry = ""  # first half of a hyphenated word waiting for the next line
        b_conf = 0.0
        b_chars = 0
        for tl in tb:
            if _local(tl.tag) != "TextLine":
                continue
            words: list[str] = []
            for el in tl:
                kind = _local(el.tag)
                if kind == "String":
                    w = normalize(el.get("CONTENT", ""))
                    if not w:
                        continue
                    if carry:
                        w, carry = carry + w, ""
                    words.append(w)
                    wc = el.get("WC")
                    if wc is not None:
                        b_conf += float(wc) * len(w)
                        b_chars += len(w)
                elif kind == "HYP" and words:
                    carry = words.pop()
            if not words:
                continue
            lb = _box(tl)
            if lb:
                box = lb if box is None else (min(box[0], lb[0]), min(box[1], lb[1]), max(box[2], lb[2]), max(box[3], lb[3]))
            lines.append(" ".join(words))
            n_words += len(words)
            # Break on a full passage, preferring a line that ends a sentence.
            if n_words >= max_words or (n_words >= max_words * 0.6 and lines[-1].rstrip().endswith((".", "!", "?"))):
                if not carry:
                    flush(lines, box, b_conf, b_chars)
                    tot_conf += b_conf
                    tot_chars += b_chars
                    lines, box, n_words, b_conf, b_chars = [], None, 0, 0.0, 0
        if carry:
            lines.append(carry)
        flush(lines, box, b_conf, b_chars)
        tot_conf += b_conf
        tot_chars += b_chars
    return blocks, (round(tot_conf / tot_chars, 3) if tot_chars else None)
