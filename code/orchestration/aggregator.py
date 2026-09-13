"""Agent 3 — Aggregator.

Receives the QueryAnalysis, the DataDossier, the resolved evidence, and the
deterministic engine decision (a planning.Plan). It only writes the natural-language
decision_explanation grounded in the engine facts; it never alters the scored numbers.
The engine remains the source of truth for amounts, status, method, plan and dates.
"""

from __future__ import annotations

from pydantic import BaseModel

from agents import Agent, Runner

from config import SETTINGS, build_model
from tools.usage import TRACKER


class Explanation(BaseModel):
    decision_explanation: str


def build_agent() -> Agent:
    return Agent(
        name="aggregator",
        instructions=(
            "You are the Aggregator for a Buy-or-Wait financial decision. You are given the "
            "final deterministic decision facts and a reference draft explanation. Rewrite the "
            "draft into ONE decision_explanation of 2-3 sentences: plain text, a single "
            "paragraph, no newlines, no markdown, no bullet lists. Every monetary value must be "
            "shown with exactly 2 decimal places and thousands separators (e.g. 30,643.57). Use "
            "only the facts given; never change a number, date, status, method or plan, and "
            "never invent data. Amounts are in the user's home currency."
        ),
        model=build_model("aggregator"),
        model_settings=SETTINGS.model_settings(),
        output_type=Explanation,
    )


def _fmt_plan(plan_str: str) -> str:
    return plan_str if plan_str else "none"


def explain(state, plan, facts: dict, draft: str = "") -> str:
    facts_brief = {
        "home_currency": state.profile.home_currency,
        "current_available_balance": state.profile.current_available_balance,
        "minimum_balance_to_keep": state.profile.minimum_balance_to_keep,
        "requested_amount": state.requested_amount,
        "amount_safe_to_pay": plan.amount_safe_to_pay,
        "affordability_status": plan.status,
        "recommended_payment_method": plan.method,
        "payment_plan": _fmt_plan(plan.plan_string()),
        "earliest_date_for_full_payment": plan.earliest_full_date.isoformat() if plan.earliest_full_date else "",
        "spending_changes_needed": plan.spending_changes_needed,
        "financial_priorities": state.profile.financial_priorities,
        "evidence_highlights": facts.get("highlights", []),
    }
    lines = "\n".join(f"{k}: {v}" for k, v in facts_brief.items())
    prompt = "Decision facts:\n" + lines
    if draft:
        prompt += "\n\nReference draft (polish wording only; keep every number and date):\n" + draft
    result = Runner.run_sync(build_agent(), prompt)
    if result.raw_responses:
        TRACKER.record(SETTINGS.model_for("aggregator"), result.raw_responses[-1].usage)
    return result.final_output.decision_explanation.strip()
