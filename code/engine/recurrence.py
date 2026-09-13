"""Conservative recurring-flow detection from settled event history.

Cash flows are aggregated to a MONTHLY cadence so weekly variable spending is not
projected as a dozen separate hits. A category is recurring only when it appears in
at least two distinct calendar months of history. The projected amount is the median
monthly total in home currency. One-off purchases, transfers, refunds, and investment
valuations are excluded.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from engine.state import Event, UserFinancialState, to_home

NON_RECURRING_TYPES = {"investment_valuation", "investment_sale", "refund", "investment_purchase"}


@dataclass
class RecurringFlow:
    category: str
    direction: str  # debit | credit
    amount_home: float  # monthly total, positive magnitude
    interval_days: int  # 30 (monthly)
    next_date: date


def detect_recurring(state: UserFinancialState) -> list[RecurringFlow]:
    as_of = state.request_date
    monthly: dict[tuple[str, str], dict[tuple[int, int], list[float]]] = defaultdict(lambda: defaultdict(list))
    months_seen: dict[tuple[str, str], set] = defaultdict(set)
    future_dates: dict[tuple[str, str], list[date]] = defaultdict(list)
    hist_last: dict[tuple[str, str], date] = {}

    superseded = state.superseded_event_ids()
    for e in state.events:
        if e.event_id in superseded:
            continue
        # Scheduled occurrences (e.g. the next confirmed salary) are a known repeat of
        # a recurring flow and count toward cadence; forecast de-dupes them from one-time.
        if e.status not in ("settled", "scheduled") or e.direction not in ("debit", "credit"):
            continue
        if e.event_type in NON_RECURRING_TYPES or e.amount is None or not e.event_date:
            continue
        key = (e.category, e.direction)
        ym = (e.event_date.year, e.event_date.month)
        home = to_home(state, e.amount, e.currency, e.settlement_date or e.event_date)
        if home > 0:
            monthly[key][ym].append(home)
            months_seen[key].add(ym)
        if e.event_date > as_of:
            future_dates[key].append(e.event_date)
        else:
            hist_last[key] = max(hist_last.get(key, e.event_date), e.event_date)

    flows: list[RecurringFlow] = []
    for key in sorted(monthly):
        if len(months_seen[key]) < 2:
            continue
        month_totals = sorted(sum(v) for v in monthly[key].values())
        median_month = month_totals[len(month_totals) // 2]
        if median_month <= 0:
            continue
        if future_dates[key]:
            nxt = min(future_dates[key])
        else:
            last = hist_last.get(key, as_of)
            nxt = last + timedelta(days=30)
            while nxt <= as_of:
                nxt += timedelta(days=30)
        flows.append(RecurringFlow(key[0], key[1], median_month, 30, nxt))
    return flows
