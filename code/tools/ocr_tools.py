"""RapidOCR-backed text extraction for supporting images.

Extracts raw text from dataset/media/images/<image_id>.png and caches results so an
image is only re-processed when a new extraction is requested. Never reads the
dataset CSVs; the caller resolves which image files to process.
"""

from __future__ import annotations

import csv
import io

from config import SETTINGS
from tools import cache

_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        from rapidocr import RapidOCR

        _ENGINE = RapidOCR()
    return _ENGINE


def _image_path(image_id: str):
    return SETTINGS.dataset_dir / "media" / "images" / f"{image_id}.png"


def extract_lines(image_id: str) -> list[str]:
    """Return OCR text lines for an image, using the markdown cache when present."""
    cached = cache.lookup("vision_ocr", image_id)
    if cached is not None:
        return [ln for ln in cached.splitlines() if ln.strip()]
    path = _image_path(image_id)
    if not path.exists():
        return []
    result = _engine()(str(path))
    lines = [str(t).strip() for t in (getattr(result, "texts", None) or []) if str(t).strip()]
    cache.upsert("vision_ocr", image_id, "\n".join(lines))
    return lines


def save_ocr_csv(image_id: str, lines: list[str]) -> str:
    """Write extracted lines to a per-image CSV under code/output/_ocr/ and return path."""
    out_dir = SETTINGS.code_output_dir / "_ocr"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{image_id}.csv"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["line_no", "text"])
    for i, ln in enumerate(lines, 1):
        w.writerow([i, ln])
    out.write_text(buf.getvalue())
    return str(out)
