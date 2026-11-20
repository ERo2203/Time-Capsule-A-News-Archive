"""Run OCR yourself on newspaper scans (JPEG/PNG/TIFF) with Tesseract.

Install the extra and the engine first::

    pip install "timecapsule[ocr]"
    sudo apt-get install tesseract-ocr      # or: brew install tesseract

Newspaper pages are dense multi-column layouts, so we ask Tesseract for its
paragraph blocks (``image_to_data``) and keep each block's position and mean
confidence, the same shape we get from ALTO.
"""

from __future__ import annotations

from pathlib import Path

from ..models import Block
from .clean import normalize


def _preprocess(img):
    from PIL import ImageOps

    img = ImageOps.exif_transpose(img).convert("L")
    img = ImageOps.autocontrast(img, cutoff=1)
    # Microfilm scans are often small; Tesseract prefers ~300 dpi text height.
    if img.width < 2500:
        scale = 2500 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    return img


def ocr_image(path: str | Path, lang: str = "eng") -> tuple[list[Block], float | None]:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise SystemExit('OCR needs the optional extra: pip install "timecapsule[ocr]"') from e

    img = _preprocess(Image.open(path))
    W, H = img.size
    data = pytesseract.image_to_data(
        img, lang=lang, config="--oem 1 --psm 1", output_type=pytesseract.Output.DICT
    )
    groups: dict[tuple[int, int], dict] = {}
    for i, word in enumerate(data["text"]):
        word = normalize(word or "").strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i])
        g = groups.setdefault(key, {"lines": {}, "box": [W, H, 0, 0], "conf": 0.0, "n": 0})
        g["lines"].setdefault(data["line_num"][i], []).append(word)
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        b = g["box"]
        b[0], b[1] = min(b[0], x), min(b[1], y)
        b[2], b[3] = max(b[2], x + w), max(b[3], y + h)
        g["conf"] += conf * len(word)
        g["n"] += len(word)

    blocks, tot, n = [], 0.0, 0
    for g in groups.values():
        text = "\n".join(" ".join(ws) for _, ws in sorted(g["lines"].items()))
        x0, y0, x1, y1 = g["box"]
        bbox = (
            round(100 * x0 / W, 2), round(100 * y0 / H, 2),
            round(100 * (x1 - x0) / W, 2), round(100 * (y1 - y0) / H, 2),
        )
        conf = g["conf"] / g["n"] / 100 if g["n"] else None
        blocks.append(Block(text=text, bbox=bbox, confidence=round(conf, 3) if conf else None))
        tot += g["conf"]
        n += g["n"]
    blocks.sort(key=lambda b: (b.bbox[0] // 12, b.bbox[1]))  # rough column-major reading order
    return blocks, (round(tot / n / 100, 3) if n else None)
