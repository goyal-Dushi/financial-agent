"""Enumerate eligible payment methods, rank safe plans, and format the output row.

Ranking precedence (details.md:46-53):
  1 complete by desired_completion_date, 2 no spending changes, 3 minimize total paid,
  4 start earlier, 5 fewer payments, 6 lowest payment_option_id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from engine import forecast
from engine.state import UserFinancialState, to_home


@dataclass
class Plan:
    method: str  # full_payment | partial_payment | installments | wait | not_recommended
    payments: list[tuple[date, float]] = field(default_factory=list)
    status: str = "not_affordable"
    total_paid: float = 0.0
    start_date: date | None = None
    needs_spending_change: bool = False
    payment_option_id: str = ""
    amount_safe_to_pay: float = 0.0
    earliest_full_date: date | None = None
    spending_changes_needed: str = "none"

    def completes_by(self, deadline: date | None) -> bool:
        if not self.payments:
            return False
        last = max(d for d, _ in self.payments)
        return deadline is None or last <= deadline

    def plan_string(self) -> str:
        if not self.payments:
            return "none"
        return "|".join(f"{d.isoformat()}:{round(a, 2)}" for d, a in sorted(self.payments))


def _safe(state: UserFinancialState, payments: list[tuple[date, float]]) -> bool:
    extra = {}
    for d, a in payments:
        extra[d] = extra.get(d, 0.0) - a
    curve = forecast.build_curve(state, extra=extra)
    return curve.min_balance() >= state.profile.minimum_balance_to_keep - 1e-6


def _date_str(d: date | None) -> str:
    return d.isoformat() if d else ""


def decide(state: UserFinancialState) -> Plan:
    request = state.request
    requested = state.requested_amount
    methods = state.profile.payment_methods
    rd = state.request_date
    deadline = state.desired_completion_date

    amount_safe = forecast.amount_safe_to_pay(state, requested)
    earliest_full = forecast.earliest_full_payment_date(state, requested)

    candidates: list[Plan] = []

    # full_payment today
    if "full_payment" in methods and amount_safe >= requested - 1e-6 and _safe(state, [(rd, requested)]):
        candidates.append(
            Plan(
                method="full_payment",
                payments=[(rd, requested)],
                status="affordable_now",
                total_paid=requested,
                start_date=rd,
                amount_safe_to_pay=amount_safe,
                earliest_full_date=rd,
            )
        )

    # installments — must exactly match a supplied option
    for opt in state.options:
        if opt.payment_method != "installments":
            continue
        if "installments" not in methods:
            continue
        if state.profile.max_installment_months is not None:
            if opt.first_payment_date and earliest_span_months(opt) > state.profile.max_installment_months:
                continue
        sched = _installment_schedule(opt)
        if not sched:
            continue
        if not _safe(state, sched):
            continue
        total = opt.total_payable_amount or sum(a for _, a in sched)
        candidates.append(
            Plan(
                method="installments",
                payments=sched,
                status="affordable_with_plan",
                total_paid=total,
                start_date=sched[0][0],
                payment_option_id=opt.payment_option_id,
                amount_safe_to_pay=amount_safe,
                earliest_full_date=earliest_full,
            )
        )

    # partial_payment — two payments, need not match an option
    if state.allows_partial and "partial_payment" in methods and 0 < amount_safe < requested and earliest_full and earliest_full <= (deadline or rd):
        second = round(requested - amount_safe, 2)
        partial = [(rd, amount_safe), (earliest_full, second)]
        if _safe(state, partial):
            candidates.append(
                Plan(
                    method="partial_payment",
                    payments=partial,
                    status="affordable_with_plan",
                    total_paid=requested,
                    start_date=rd,
                    amount_safe_to_pay=amount_safe,
                    earliest_full_date=earliest_full,
                )
            )

    # wait — full becomes safe later, user accepts full_payment
    if "full_payment" in methods and earliest_full and earliest_full > rd and (deadline is None or earliest_full <= deadline):
        if _safe(state, [(earliest_full, requested)]):
            candidates.append(
                Plan(
                    method="wait",
                    payments=[(earliest_full, requested)],
                    status="affordable_later",
                    total_paid=requested,
                    start_date=earliest_full,
                    amount_safe_to_pay=amount_safe,
                    earliest_full_date=earliest_full,
                )
            )

    if not candidates:
        return Plan(
            method="not_recommended",
            payments=[],
            status="not_affordable",
            total_paid=0.0,
            amount_safe_to_pay=amount_safe,
            earliest_full_date=earliest_full,
        )

    # Rank.
    def sort_key(p: Plan):
        return (
            not p.completes_by(deadline),      # prefer completes by deadline
            p.needs_spending_change,           # prefer no spending changes
            round(p.total_paid, 2),            # minimize total paid
            p.start_date or date.max,          # start earlier
            len(p.payments),                   # fewer payments
            p.payment_option_id or "zzz",      # lowest option id
        )

    candidates.sort(key=sort_key)
    return candidates[0]


def earliest_span_months(opt) -> float:
    if not opt.first_payment_date or opt.number_of_payments <= 1:
        return 0.0
    last = opt.first_payment_date + timedelta(days=opt.payment_frequency_days * (opt.number_of_payments - 1))
    return (last - opt.first_payment_date).days / 30.0


def _installment_schedule(opt) -> list[tuple[date, float]] | None:
    if not opt.first_payment_date or not opt.payment_amount:
        return None
    n = opt.number_of_payments or 1
    per = round(opt.payment_amount, 2)
    return [(opt.first_payment_date + timedelta(days=opt.payment_frequency_days * i), per) for i in range(n)]
