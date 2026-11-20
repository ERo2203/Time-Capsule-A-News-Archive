"""Bring your own scans: OCR a folder of newspaper page images with Tesseract.

Expected layout (one sidecar JSON per image gives the citation)::

    my_scans/
      bombay-chronicle-1919-04-14-p1.jpg
      bombay-chronicle-1919-04-14-p1.json   {"newspaper": "The Bombay Chronicle",
                                              "place": "Bombay", "date": "1919-04-14",
                                              "page": 1, "url": "https://...", "rights": "..."}

Without a sidecar the file name is used as the newspaper name and the date is
left blank, which keeps the passage searchable but weak as a citation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from ..models import Page

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".jp2"}


def fetch(folder: str | Path, lang: str = "eng", collection: str = "") -> Iterator[Page]:
    from ..ocr.tesseract import ocr_image

    for img in sorted(Path(folder).iterdir()):
        if img.suffix.lower() not in IMAGE_EXT:
            continue
        meta_path = img.with_suffix(".json")
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        blocks, conf = ocr_image(img, lang=lang)
        yield Page(
            id=f"local:{img.stem}",
            source="local",
            newspaper=meta.get("newspaper", img.stem),
            place=meta.get("place", ""),
            date=meta.get("date", ""),
            page=meta.get("page"),
            url=meta.get("url", img.resolve().as_uri()),
            text="\n\n".join(b.text for b in blocks),
            language=lang[:2],
            ocr_confidence=conf,
            ocr_engine="Tesseract (local)",
            rights=meta.get("rights", ""),
            collection=collection or meta.get("collection", ""),
            blocks=blocks,
        )
