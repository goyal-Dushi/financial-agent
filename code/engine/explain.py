"""Grounded, spec-compliant decision explanations.

schema.md requires a *short* explanation of the recommendation and the financial
facts behind it. This module composes a single-paragraph, 2-3 sentence
explanation (no newlines, no markdown) purely from deterministic engine facts.
The LLM Aggregator may polish the wording but never changes a number or a date.
"""

from __future__ import annotations

from datetime import date

from engine import recurrence
from engine.state import UserFinancialState


def _fmt(x: float) -> str:
    return f"{x:,.2f}"


def _d(d: date | None) -> str:
    return d.strftime("%d %b %Y") if d else ""


def _financing_fee(state: UserFinancialState, plan) -> float:
    if not plan.payment_option_id:
        return 0.0
    for opt in state.options:
        if opt.payment_option_id == plan.payment_option_id:
            return opt.financing_fee or 0.0
    return 0.0


def _deadline(state: UserFinancialState) -> str:
    return _d(state.desired_completion_date) or "the 90-day horizon"


def _recommendation(state: UserFinancialState, plan) -> str:
    cur = state.profile.home_currency
    req = _fmt(state.requested_amount)
    deadline = _deadline(state)

    if plan.method == "full_payment":
        return f"Recommendation: pay the full {req} {cur} today ({_d(state.request_date)})."

    if plan.method == "installments":
        n = len(plan.payments)
        per = _fmt(plan.payments[0][1])
        first, last = plan.payments[0][0], plan.payments[-1][0]
        fee = _financing_fee(state, plan)
        if plan.payment_option_id:
            detail = f" ({plan.payment_option_id}"
            if fee:
                detail += f", includes a {_fmt(fee)} {cur} financing fee"
            detail += ")"
        elif fee:
            detail = f" (includes a {_fmt(fee)} {cur} financing fee)"
        else:
            detail = ""
        return (
            f"Recommendation: pay {n} installments of {per} {cur} from {_d(first)} to "
            f"{_d(last)}{detail}, completing the {req} {cur} request by the {deadline} deadline."
        )

    if plan.method == "partial_payment":
        a1 = _fmt(plan.payments[0][1])
        a2 = _fmt(plan.payments[1][1])
        return (
            f"Recommendation: pay {a1} {cur} today and the remaining {a2} {cur} on "
            f"{_d(plan.payments[1][0])}, completing the {req} {cur} request by the {deadline} deadline."
        )

    if plan.method == "wait":
        return (
            f"Recommendation: wait and pay the full {req} {cur} as a single payment on "
            f"{_d(plan.start_date)}, within the {deadline} deadline."
        )

    return (
        f"Recommendation: do not proceed with the {req} {cur} request; no available "
        f"payment option completes it safely by the {deadline} deadline."
    )


def _facts(state: UserFinancialState) -> str:
    cur = state.profile.home_currency
    flows = recurrence.detect_recurring(state)
    income = sum(f.amount_home for f in flows if f.direction == "credit")
    outflows = sum(f.amount_home for f in flows if f.direction == "debit")
    return (
        f"Financial basis: current balance {_fmt(state.profile.current_available_balance)} {cur} "
        f"against a {_fmt(state.profile.minimum_balance_to_keep)} {cur} minimum to keep; the 90-day "
        f"forecast projects recurring income of {_fmt(income)} {cur}/month and recurring outflows of "
        f"{_fmt(outflows)} {cur}/month."
    )


def _why(state: UserFinancialState, plan) -> str:
    cur = state.profile.home_currency
    req = state.requested_amount
    safe = plan.amount_safe_to_pay
    parts: list[str] = []

    if plan.method == "not_recommended":
        parts.append(
            f"only {_fmt(safe)} {cur} is safe to pay on the request date and the full "
            f"{_fmt(req)} {cur} never becomes safe within the forecast"
        )
    else:
        parts.append(f"{_fmt(safe)} {cur} is safe to pay on the request date")
        if plan.earliest_full_date:
            if plan.earliest_full_date == state.request_date and plan.method != "full_payment":
                parts.append(
                    "the full amount is already safe as a single payment but full payment is "
                    "excluded by the user's stated payment preferences"
                )
            else:
                parts.append(
                    f"the full amount is forecast safe as a single payment from {_d(plan.earliest_full_date)}"
                )
        else:
            parts.append("the full amount is not expected to become safe within the 90-day forecast")

    if plan.spending_changes_needed and plan.spending_changes_needed != "none":
        parts.append(f"spending changes required: {plan.spending_changes_needed}")
    else:
        parts.append("no spending changes are required")

    text = "; ".join(parts)
    return text[0].upper() + text[1:] + "."


def build_explanation(state: UserFinancialState, plan) -> str:
    """Compose a single-paragraph, 2-3 sentence explanation with 2-dp amounts."""
    return " ".join(
        [
            _recommendation(state, plan),
            _facts(state),
            _why(state, plan),
        ]
    )
