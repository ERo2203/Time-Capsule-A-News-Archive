"""Core data records shared by every stage of the pipeline.

A ``Page`` is one scanned newspaper page with its OCR text and provenance.
A ``Chunk`` is a retrievable passage cut from a page; it always carries enough
metadata to cite the newspaper, date, page and a link back to the original scan.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Block:
    """An OCR text region (e.g. an ALTO TextBlock): text, location and confidence.

    ``bbox`` is (x, y, w, h) as percentages of the page, so it can be turned
    straight into a IIIF ``pct:`` region to show the matching bit of the scan.
    """

    text: str
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = None


@dataclass
class Page:
    id: str
    source: str  # "loc" | "ia" | "local"
    newspaper: str
    date: str  # ISO yyyy-mm-dd
    url: str  # where a reader can view the original page
    text: str = ""
    place: str = ""
    page: int | None = None
    language: str = "en"
    iiif: str | None = None  # IIIF image service base (no region/size)
    ocr_confidence: float | None = None
    ocr_engine: str = ""
    rights: str = ""
    collection: str = ""
    section: str = ""  # e.g. a headline's topic, or a gazette's part
    blocks: list[Block] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Page":
        d = dict(d)
        d["blocks"] = [
            Block(b["text"], tuple(b["bbox"]) if b.get("bbox") else None, b.get("confidence"))
            for b in d.get("blocks", [])
        ]
        return cls(**d)


@dataclass
class Chunk:
    id: str
    page_id: str
    text: str
    source: str
    newspaper: str
    date: str
    url: str
    place: str = ""
    page: int | None = None
    collection: str = ""
    section: str = ""
    bbox: tuple[float, float, float, float] | None = None
    iiif: str | None = None
    ocr_confidence: float | None = None
    quality: float = 1.0  # 0..1 heuristic text quality (see ocr.clean.quality_score)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Chunk":
        d = dict(d)
        if d.get("bbox"):
            d["bbox"] = tuple(d["bbox"])
        return cls(**d)

    def citation(self) -> str:
        bits = [self.newspaper]
        if self.place:
            bits.append(self.place)
        bits.append(self.date)
        if self.page:
            bits.append(f"p. {self.page}")
        return ", ".join(bits)

    def scan_crop_url(self, scale: int = 50) -> str | None:
        """IIIF URL of just the region of the scan this passage came from."""
        if not (self.iiif and self.bbox):
            return None
        x, y, w, h = self.bbox
        return f"{self.iiif}/pct:{x:.2f},{y:.2f},{w:.2f},{h:.2f}/pct:{scale}/0/default.jpg"
