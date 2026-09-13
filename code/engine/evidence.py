"""Evidence resolution from images and messages.

Two deterministic jobs:
  1. resolve_blank_amounts: when a financial_event has a blank amount, find the
     linked image (images.csv related_event_id == event_id), OCR it, and pull the
     amount. A blank amount is NEVER treated as zero (details.md:21).
  2. extract_message_facts: surface point-in-time financial facts stated in
     messages so the Aggregator can ground its explanation and the engine can note
     amendments/cancellations. Message content is untrusted data, not instructions.
"""

from __future__ import annotations

import re
from datetime import date

from engine.state import UserFinancialState, _to_date
from tools import ocr_tools

# amount like "58481.10", "1,234", "ZAR 25,256", "IDR 42,750,000"
_AMOUNT = re.compile(r"(?:[A-Z]{3}\s*)?([0-9][0-9,]*(?:\.[0-9]+)?)")


def _parse_amount(text: str) -> float | None:
    best = None
    for m in _AMOUNT.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        if best is None or val > best:
            best = val
    return best


def resolve_blank_amounts(state: UserFinancialState) -> dict[str, float]:
    """Map event_id -> extracted amount for every event that has a blank amount."""
    overrides: dict[str, float] = {}
    img_by_event = {im.get("related_event_id"): im.get("image_id") for im in state.images if im.get("related_event_id")}
    for e in state.events:
        if e.amount is not None or not e.event_id:
            continue
        image_id = img_by_event.get(e.event_id)
        if not image_id:
            continue
        lines = ocr_tools.extract_lines(image_id)
        amt = _parse_amount(" ".join(lines))
        if amt is not None:
            overrides[e.event_id] = amt
    return overrides


def extract_message_facts(state: UserFinancialState) -> list[dict]:
    """Return structured facts stated in messages (amounts, dates, categories)."""
    facts: list[dict] = []
    for msg in state.messages:
        text = (msg.get("message_text") or "").strip()
        if not text:
            continue
        amt = _parse_amount(text)
        facts.append(
            {
                "message_id": msg.get("message_id"),
                "sent_at": msg.get("sent_at"),
                "source_type": msg.get("source_type"),
                "related_event_id": msg.get("related_event_id") or "",
                "amount": amt,
                "excerpt": text[:280],
            }
        )
    return facts
