"""Reconstruct a user's financial position for a request.

Loads profiles, events, exchange rates, payment options, messages and images for
one (user, request) pair, classifies events by cash state, and converts amounts
to the user's home currency using the dated rates in exchange_rates.csv.

Amounts in event rows are stored in their native `currency`; all cash maths in the
engine is done after conversion to `home_currency`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from tools import db


def _to_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()[:10]
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def _to_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _split_pipe(value) -> list[str]:
    if value in (None, ""):
        return []
    return [p.strip() for p in str(value).split("|") if p.strip()]


@dataclass
class Event:
    event_id: str
    event_type: str
    description: str
    category: str
    direction: str
    amount: float | None
    currency: str
    event_date: date | None
    settlement_date: date | None
    status: str
    linked_event_id: str
    flexibility: str
    minimum_allowed_amount: float | None


@dataclass
class Profile:
    user_id: str
    home_currency: str
    current_available_balance: float
    minimum_balance_to_keep: float
    financial_priorities: list[str]
    protect_categories: list[str]
    reduce_categories: list[str]
    stop_categories: list[str]
    payment_methods: list[str]
    max_installment_months: int | None


@dataclass
class PaymentOption:
    payment_option_id: str
    payment_method: str
    payment_amount: float | None
    number_of_payments: int
    first_payment_date: date | None
    payment_frequency_days: int
    financing_fee: float
    total_payable_amount: float | None


@dataclass
class UserFinancialState:
    user_id: str
    request: dict
    profile: Profile
    events: list[Event]
    options: list[PaymentOption]
    messages: list[dict]
    images: list[dict]
    rates: dict = field(repr=False, default_factory=dict)

    @property
    def request_date(self) -> date:
        return _to_date(self.request["request_date"])

    @property
    def requested_amount(self) -> float:
        return float(_to_float(self.request.get("requested_amount")) or 0.0)

    @property
    def desired_completion_date(self) -> date | None:
        return _to_date(self.request.get("desired_completion_date"))

    @property
    def allows_partial(self) -> bool:
        return str(self.request.get("allows_partial_payment", "")).strip().lower() == "true"


class RateBook:
    """Dated exchange-rate lookup with nearest-prior fallback."""

    def __init__(self, rows: list[dict]):
        self.by_pair: dict[tuple[str, str], list[tuple[date, float]]] = {}
        for r in rows:
            pair = (r["from_currency"], r["to_currency"])
            rd = _to_date(r["rate_date"])
            rate = _to_float(r["rate"])
            if rd and rate is not None:
                self.by_pair.setdefault(pair, []).append((rd, rate))
        for pair in self.by_pair:
            self.by_pair[pair].sort()

    def convert(self, amount: float, frm: str, to: str, on: date | None) -> float:
        if frm == to or amount is None:
            return amount
        series = self.by_pair.get((frm, to))
        if not series:
            inv = self.by_pair.get((to, frm))
            if inv:
                rate = 1.0 / self._rate_at(inv, on)
                return amount * rate
            return amount  # no rate available; leave unchanged (foreign cash rare)
        return amount * self._rate_at(series, on)

    @staticmethod
    def _rate_at(series: list[tuple[date, float]], on: date | None) -> float:
        if on is None:
            return series[-1][1]
        best = None
        for d, rate in series:
            if d <= on:
                best = rate
            else:
                break
        return best if best is not None else series[0][1]


def load_state(user_id: str, request_id: str, amount_overrides: dict[str, float] | None = None, request_row: dict | None = None) -> UserFinancialState:
    if request_row is not None:
        request = dict(request_row)
    else:
        req_rows = db.run_sql(f"SELECT * FROM requests WHERE request_id = '{request_id}'")
        request = req_rows[0]

    prof_rows = db.run_sql(f"SELECT * FROM financial_profiles WHERE user_id = '{user_id}'")
    assert prof_rows, f"no profile for {user_id}"
    p = prof_rows[0]
    max_inst = _to_float(p.get("max_installment_months"))
    profile = Profile(
        user_id=user_id,
        home_currency=p["home_currency"],
        current_available_balance=_to_float(p["current_available_balance"]) or 0.0,
        minimum_balance_to_keep=_to_float(p["minimum_balance_to_keep"]) or 0.0,
        financial_priorities=_split_pipe(p.get("financial_priorities")),
        protect_categories=_split_pipe(p.get("expense_categories_to_protect")),
        reduce_categories=_split_pipe(p.get("expense_categories_user_is_willing_to_reduce")),
        stop_categories=_split_pipe(p.get("expense_categories_user_is_willing_to_stop")),
        payment_methods=_split_pipe(p.get("payment_methods_user_will_consider")),
        max_installment_months=int(max_inst) if max_inst is not None else None,
    )

    ev_rows = db.run_sql(
        f"SELECT * FROM financial_events WHERE user_id = '{user_id}' ORDER BY event_date"
    )
    overrides = amount_overrides or {}
    events: list[Event] = []
    for r in ev_rows:
        amt = _to_float(r.get("amount"))
        if amt is None and r["event_id"] in overrides:
            amt = overrides[r["event_id"]]
        events.append(
            Event(
                event_id=r["event_id"],
                event_type=r.get("event_type") or "",
                description=r.get("description") or "",
                category=r.get("category") or "",
                direction=(r.get("direction") or "").strip().lower(),
                amount=amt,
                currency=r.get("currency") or profile.home_currency,
                event_date=_to_date(r.get("event_date")),
                settlement_date=_to_date(r.get("settlement_date")),
                status=(r.get("status") or "").strip().lower(),
                linked_event_id=r.get("linked_event_id") or "",
                flexibility=(r.get("flexibility") or "").strip().lower(),
                minimum_allowed_amount=_to_float(r.get("minimum_allowed_amount")),
            )
        )

    opt_rows = db.run_sql(
        f"SELECT * FROM request_payment_options WHERE request_id = '{request_id}' ORDER BY payment_option_id"
    )
    options = [
        PaymentOption(
            payment_option_id=o["payment_option_id"],
            payment_method=o.get("payment_method") or "",
            payment_amount=_to_float(o.get("payment_amount")),
            number_of_payments=int(_to_float(o.get("number_of_payments")) or 1),
            first_payment_date=_to_date(o.get("first_payment_date")),
            payment_frequency_days=int(_to_float(o.get("payment_frequency_days")) or 0),
            financing_fee=_to_float(o.get("financing_fee")) or 0.0,
            total_payable_amount=_to_float(o.get("total_payable_amount")),
        )
        for o in opt_rows
    ]

    msg_rows = db.run_sql(
        f"SELECT * FROM messages WHERE user_id = '{user_id}' OR request_id = '{request_id}' ORDER BY sent_at"
    )
    img_rows = db.run_sql(
        f"SELECT * FROM images WHERE user_id = '{user_id}' OR request_id = '{request_id}'"
    )
    rate_rows = db.run_sql("SELECT * FROM exchange_rates")

    return UserFinancialState(
        user_id=user_id,
        request=request,
        profile=profile,
        events=events,
        options=options,
        messages=msg_rows,
        images=img_rows,
        rates=RateBook(rate_rows),
    )


def to_home(state: UserFinancialState, amount: float | None, currency: str, on: date | None) -> float:
    if amount is None:
        return 0.0
    return state.rates.convert(amount, currency, state.profile.home_currency, on)
