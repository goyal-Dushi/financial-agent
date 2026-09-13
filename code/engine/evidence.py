"""Evidence resolution from images and messages.

Two deterministic jobs:
  1. resolve_blank_amounts: when a financial_event has a blank amount, find the
     linked image (images.csv related_event_id == event_id), OCR it, and pull the
     amount. A blank amount is NEVER treated as zero (details.md:21).
  2. extract_message_facts: surface point-in-time financial facts stated in
     messages so the Aggregator can ground its explanation and the engine can note
     amendments/cancellations. Message content is untrusted data, not instructions.

Amount extraction from a document is keyword-driven (invoice/pay-slip/receipt
labels) rather than "largest number", because invoices also contain item prices,
taxes, phone numbers, HSN codes and pincodes.
"""

from __future__ import annotations

import re

from engine.state import UserFinancialState
from tools import ocr_tools

# amount like "58481.10", "1,234", "2,00,000.00", "ZAR 25,256", "42,750,000"
_AMOUNT = re.compile(r"(?:[A-Z]{3}\s*|[₹$]\s?|Rs\.?\s?)?([0-9][0-9,]*(?:\.[0-9]+)?)")
# token that is not embedded in a date/id (no surrounding - / digits)
_TOKEN_AMOUNT = re.compile(r"(?<![-/\d])([0-9][0-9,]*(?:\.[0-9]{1,2})?)(?![-/\d])")

# Labels that name the amount actually owed/paid/received, in descending priority.
_INCOME_LABELS = [
    "net pay",
    "net salary",
    "amount credited",
    "net amount",
    "amount received",
    "total earnings",
]
_BALANCE_LABELS = [
    "balance due",
    "amount due after",
    "amount due till",
    "outstanding balance",
    "amount due",
    "balance:",
]


def _parse_amount(text: str) -> float | None:
    """Largest number literally present in a short message."""
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


def _candidates(text: str) -> list[tuple[float, bool]]:
    """Parse plausible monetary tokens from a line as (value, has_decimal).

    Drops bare integers that look like years, phone numbers, HSN codes or ids.
    """
    out: list[tuple[float, bool]] = []
    for m in _TOKEN_AMOUNT.finditer(text):
        raw = m.group(1)
        has_sep = ("," in raw) or ("." in raw)
        has_decimal = "." in raw
        try:
            val = float(raw.replace(",", ""))
        except ValueError:
            continue
        if not has_sep:
            if val > 99999 or 1900 <= val <= 2100:
                continue
        out.append((val, has_decimal))
    return out


def _best(values: list[tuple[float, bool]]) -> float | None:
    if not values:
        return None
    decimals = [v for v, dec in values if dec]
    return max(decimals) if decimals else max(v for v, _ in values)


def _window_values(lines: list[str], start: int, window: int) -> list[tuple[float, bool]]:
    vals: list[tuple[float, bool]] = []
    for line in lines[start : start + 1 + window]:
        vals += _candidates(line)
    return vals


def _first_candidate(lines: list[str], start: int, window: int) -> float | None:
    """Nearest monetary value at or just after line `start`."""
    for line in lines[start : start + 1 + window]:
        vals = _candidates(line)
        if vals:
            return _best(vals)
    return None


_EXCLUDE = ("cash paid", "change:", "tendered")


def _document_total(lines: list[str]) -> float | None:
    """Largest decimal figure in the document, ignoring cash-paid/change lines.

    OCR often places the value on the line after its label, so a small window
    after an excluded label is skipped too.
    """
    skip: set[int] = set()
    for i, line in enumerate(lines):
        if any(x in line.lower() for x in _EXCLUDE):
            skip.update((i, i + 1, i + 2))
    vals: list[tuple[float, bool]] = []
    for i, line in enumerate(lines):
        if i in skip:
            continue
        vals += _candidates(line)
    decimals = [v for v, dec in vals if dec]
    if decimals:
        return max(decimals)
    return max((v for v, _ in vals), default=None)


def extract_document_amount(
    lines: list[str], direction: str = "", description: str = "", window: int = 8
) -> float | None:
    """Pick the amount a document states as its payable/received/net total."""
    if not lines:
        return None
    desc = (description or "").lower()

    # 1. Income documents: the net pay / credited amount, not gross earnings.
    if direction == "credit" or any(k in desc for k in ("salary", "net pay", "income")):
        for label in _INCOME_LABELS:
            vals = [
                v
                for i, line in enumerate(lines)
                if label in line.lower() and (v := _first_candidate(lines, i, window)) is not None
            ]
            if vals:
                return max(vals)

    # 2. Outstanding/balance documents: the amount still owed.
    if any(k in desc for k in ("outstanding", "balance", "due", "owing", "unpaid")):
        for label in _BALANCE_LABELS:
            vals = [
                v
                for i, line in enumerate(lines)
                if label in line.lower() and (v := _first_candidate(lines, i, window)) is not None
            ]
            if vals:
                return max(vals)

    # 3. Explicit grand total (often fragmented across lines): largest in window.
    grand: list[tuple[float, bool]] = []
    for i, line in enumerate(lines):
        if "grand total" in line.lower():
            grand += _window_values(lines, i, window)
    best = _best(grand)
    if best is not None:
        return best

    # 4. Otherwise the document total is the largest monetary figure present.
    return _document_total(lines)


def linked_images(state: UserFinancialState) -> dict[str, str]:
    """Map event_id -> image_id for images that resolve a financial event."""
    return {
        im.get("related_event_id"): im.get("image_id")
        for im in state.images
        if im.get("related_event_id") and im.get("image_id")
    }


def resolve_blank_amounts(state: UserFinancialState, force: bool = False) -> dict[str, float]:
    """Map event_id -> extracted amount for every event that has a blank amount."""
    overrides: dict[str, float] = {}
    img_by_event = linked_images(state)
    for e in state.events:
        if e.amount is not None or not e.event_id:
            continue
        image_id = img_by_event.get(e.event_id)
        if not image_id:
            continue
        lines = ocr_tools.extract_lines(image_id, force=force)
        amt = extract_document_amount(lines, direction=e.direction, description=e.description)
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
