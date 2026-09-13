"""90-day daily balance projection.

Starts from current_available_balance and walks forward applying scheduled/pending
debits, projected recurring income & essentials, and any payment under test. A plan
is safe only if the balance never dips below minimum_balance_to_keep.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from engine import recurrence
from engine.state import UserFinancialState, to_home

HORIZON_DAYS = 90
_IGNORE_STATUS = {"cancelled", "failed", "unrealized"}


@dataclass
class BalanceCurve:
    start: date
    end: date
    daily: dict[date, float]

    def min_balance(self) -> float:
        return min(self.daily.values())

    def balance_on(self, d: date) -> float:
        return self.daily.get(d, self.daily[self.start])


def _one_time_future_flows(state: UserFinancialState, end: date, recurring_keys: set[tuple[str, str]]) -> dict[date, float]:
    """Scheduled + pending-debit cash flows not already covered by a recurring flow."""
    as_of = state.request_date
    buckets: dict[date, float] = defaultdict(float)
    superseded = state.superseded_event_ids()
    for e in state.events:
        if e.event_id in superseded:
            continue
        if e.direction not in ("debit", "credit") or e.status in _IGNORE_STATUS or e.amount is None:
            continue
        when = e.settlement_date or e.event_date
        if when is None or when <= as_of or when > end:
            continue
        if (e.category, e.direction) in recurring_keys:
            continue  # already projected by the recurring model
        if e.status == "pending" and e.direction == "credit":
            continue  # pending credits are not counted until settled
        signed = to_home(state, e.amount, e.currency, when)
        buckets[when] += signed if e.direction == "credit" else -signed
    return buckets


def build_curve(state: UserFinancialState, extra: dict[date, float] | None = None) -> BalanceCurve:
    start = state.request_date
    end = start + timedelta(days=HORIZON_DAYS)

    flows = recurrence.detect_recurring(state)
    recurring_keys = {(f.category, f.direction) for f in flows}

    deltas: dict[date, float] = defaultdict(float)
    for d, amt in _one_time_future_flows(state, end, recurring_keys).items():
        deltas[d] += amt

    for f in flows:
        d = f.next_date
        while d is not None and d <= end:
            if d > start:
                deltas[d] += f.amount_home if f.direction == "credit" else -f.amount_home
            d = d + timedelta(days=f.interval_days)

    if extra:
        for d, amt in extra.items():
            deltas[d] += amt

    daily: dict[date, float] = {}
    bal = state.profile.current_available_balance
    for i in range(HORIZON_DAYS + 1):
        d = start + timedelta(days=i)
        bal += deltas.get(d, 0.0)
        daily[d] = bal
    return BalanceCurve(start=start, end=end, daily=daily)


def amount_safe_to_pay(state: UserFinancialState, requested_amount: float) -> float:
    """Largest amount payable on request_date keeping balance >= min across the horizon."""
    base = build_curve(state)
    headroom = base.min_balance() - state.profile.minimum_balance_to_keep
    return max(0.0, min(requested_amount, round(headroom, 2)))


def earliest_full_payment_date(state: UserFinancialState, full_amount: float) -> date | None:
    """Earliest date a single full payment stays safe to the end of the horizon."""
    base = build_curve(state)
    min_keep = state.profile.minimum_balance_to_keep
    days = sorted(base.daily)
    # suffix_min[d] = min balance from d to end
    suffix_min: dict[date, float] = {}
    running = float("inf")
    for d in reversed(days):
        running = min(running, base.daily[d])
        suffix_min[d] = running
    for d in days:
        if base.balance_on(d) >= full_amount and suffix_min[d] - full_amount >= min_keep - 1e-6:
            return d
    return None
