"""RapidOCR-backed text extraction for supporting images.

Extracts raw text from dataset/media/images/<image_id>.png using the local
RapidOCR (ONNX) engine — no API key or network call. Results are cached under
code/cache/vision_ocr.md keyed by image_id so an image is only re-processed when
its text is missing or a refresh (override) is explicitly requested.

Never reads the dataset CSVs; the caller resolves which image files to process.
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


def _run_ocr(image_id: str) -> list[str]:
    """Run RapidOCR on one image and return non-empty text lines."""
    path = _image_path(image_id)
    if not path.exists():
        return []
    result = _engine()(str(path))
    # RapidOCR exposes recognized strings on `.txts` (older builds used `.texts`);
    # tolerate both plus the dict form of newer result objects.
    raw = getattr(result, "txts", None)
    if raw is None:
        raw = getattr(result, "texts", None)
    if raw is None and hasattr(result, "to_dict"):
        try:
            raw = (result.to_dict() or {}).get("txts")
        except Exception:
            raw = None
    return [str(t).strip() for t in (raw or []) if str(t).strip()]


def extract_lines(image_id: str, force: bool = False) -> list[str]:
    """Return OCR text lines for an image.

    Uses the markdown cache when a non-empty extraction is stored. When `force`
    is True the image is re-processed and the cached entry is overwritten
    (the override provision). Empty results are never cached so a transient OCR
    miss does not permanently poison the cache.
    """
    if not force:
        cached = cache.lookup("vision_ocr", image_id)
        if cached:  # non-empty body only
            return [ln for ln in cached.splitlines() if ln.strip()]
    lines = _run_ocr(image_id)
    if lines:
        cache.upsert("vision_ocr", image_id, "\n".join(lines))
    return lines


def refresh_image(image_id: str) -> list[str]:
    """Force re-OCR of an image and overwrite any cached text (override)."""
    return extract_lines(image_id, force=True)


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
