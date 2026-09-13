"""Output invariant checks (problem_statement.md:107-163).

Guarantees every written row satisfies the hard relationships before it is appended.
Raises ValidationReport.errors when violated so main.py can repair or flag.
"""

from __future__ import annotations

from datetime import date


def _pdate(s: str) -> date | None:
    try:
        y, m, d = str(s)[:10].split("-")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def validate_row(row: dict, request: dict) -> list[str]:
    errors: list[str] = []
    req_amt = float(request["requested_amount"])
    amt = float(row["amount_safe_to_pay"])
    status = row["affordability_status"]
    method = row["recommended_payment_method"]
    plan = row["payment_plan"]
    earliest = row["earliest_date_for_full_payment"]

    if not (0 <= amt <= req_amt + 1e-6):
        errors.append(f"amount_safe_to_pay {amt} outside [0,{req_amt}]")

    if status not in {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}:
        errors.append(f"bad affordability_status {status}")
    if method not in {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}:
        errors.append(f"bad recommended_payment_method {method}")

    if status == "affordable_now" and _pdate(earliest) != _pdate(request["request_date"]):
        errors.append("affordable_now requires earliest_date == request_date")

    if method == "partial_payment":
        if status != "affordable_with_plan":
            errors.append("partial_payment requires affordable_with_plan")
        parts = plan.split("|")
        if len(parts) != 2:
            errors.append("partial_payment must have exactly two payments")
        else:
            total = sum(float(p.split(":")[1]) for p in parts)
            if abs(total - req_amt) > 0.5:
                errors.append(f"partial payments sum {total} != requested {req_amt}")

    if method == "wait" and status != "affordable_later":
        errors.append("wait generally pairs with affordable_later")
    if method == "not_recommended" and plan != "none":
        errors.append("not_recommended plan must be none")
    if method != "not_recommended" and plan != "none":
        for p in plan.split("|"):
            if ":" not in p or _pdate(p.split(":")[0]) is None:
                errors.append(f"malformed payment_plan segment {p}")

    changes = row.get("spending_changes_needed", "none")
    if changes != "none":
        segs = changes.split("|")
        if len(segs) > 3:
            errors.append("more than three spending changes")
        stopped, reduced = set(), set()
        for s in segs:
            if s.startswith("stop:"):
                stopped.add(s.split(":")[1])
            elif s.startswith("reduce_to:"):
                _, eid, *_ = s.split(":")
                reduced.add(eid)
            else:
                errors.append(f"bad spending change {s}")
        both = stopped & reduced
        if both:
            errors.append(f"stop and reduce same event: {both}")

    return errors
