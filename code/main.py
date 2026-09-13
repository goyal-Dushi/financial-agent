"""Buy or Wait? — single entry point.

python main.py                # full 250-request run -> repo-root output.csv
python main.py --limit 5      # first 5 requests
python main.py --request-id request_26
python main.py --skip-agents  # deterministic engine only (no LLM calls)
python main.py --sample       # run the 25 public examples for self-check

Each request flows through the chain:
  1. Query Analyser  -> structured intent
  2. Data Generator  -> per-user CSV extracts (+ Vision/OCR agent for image evidence)
  3. Deterministic engine (evidence -> state -> recurrence -> forecast -> planning)
  4. Aggregator      -> grounded decision_explanation
  5. Validation      -> invariant check before the row is appended
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from config import SETTINGS
from engine import evidence, explain as explainer, planning, state as S, validation
from tools import db
from tools import ocr_tools
from tools.usage import TRACKER

QUIET = False


def log_step(request_id: str | None, user_id: str | None, stage: str, message: str) -> None:
    """Emit a progress line. Never logs financial data, only step + identifiers."""
    if QUIET:
        return
    ts = datetime.now().strftime("%H:%M:%S")
    ctx = f" [{request_id} | {user_id}]" if request_id else ""
    print(f"{ts} [{stage}]{ctx} {message}", flush=True)

OUTPUT_COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]


def _load_requests(limit: int | None, only_request_id: str | None, sample: bool) -> list[dict]:
    if sample:
        rows = list(csv.DictReader(open(SETTINGS.dataset_dir / "sample_requests.csv")))
    else:
        rows = db.load_all_users()
    if only_request_id:
        rows = [r for r in rows if r["request_id"] == only_request_id]
    if limit:
        rows = rows[:limit]
    return rows


def build_row(request: dict, use_agents: bool) -> dict:
    user_id = request["user_id"]
    request_id = request["request_id"]

    if use_agents:
        from orchestration import aggregator, data_generator, query_analyser

        try:
            log_step(request_id, user_id, "Query Analyser", "analysing request intent")
            query_analyser.analyse(request)
            log_step(request_id, user_id, "Data Generator", "gathering per-user data (Vision/OCR)")
            data_generator.generate(_analysis_stub(request), user_id, request_id)
        except Exception as exc:  # keep the run going; engine is authoritative
            log_step(request_id, user_id, "Agents", "degraded; using deterministic engine")
            print(f"  [warn] agent stage degraded for {request_id}: {exc}", file=sys.stderr)

    # Deterministic: resolve blank amounts from images, then load state with overrides.
    log_step(request_id, user_id, "Evidence", "resolving blank amounts from images/messages")
    prelim = S.load_state(user_id, request_id, request_row=request)
    overrides = evidence.resolve_blank_amounts(prelim)
    log_step(request_id, user_id, "State", "reconstructing financial position")
    state = S.load_state(user_id, request_id, amount_overrides=overrides, request_row=request)
    facts = {"highlights": [m["excerpt"] for m in evidence.extract_message_facts(state)][:3]}

    log_step(request_id, user_id, "Planning", "running 90-day forecast and plan ranking")
    plan = planning.decide(state)

    deterministic = explainer.build_explanation(state, plan)
    explanation = ""
    if use_agents:
        from orchestration import aggregator

        try:
            log_step(request_id, user_id, "Aggregator", "composing decision explanation")
            explanation = aggregator.explain(state, plan, facts, draft=deterministic)
        except Exception as exc:
            log_step(request_id, user_id, "Aggregator", "degraded; using deterministic text")
            print(f"  [warn] aggregator degraded for {request_id}: {exc}", file=sys.stderr)
    if not explanation:
        explanation = deterministic

    row = {
        "request_id": request_id,
        "amount_safe_to_pay": round(plan.amount_safe_to_pay, 2),
        "affordability_status": plan.status,
        "recommended_payment_method": plan.method,
        "payment_plan": plan.plan_string(),
        "earliest_date_for_full_payment": plan.earliest_full_date.isoformat() if plan.earliest_full_date else "",
        "spending_changes_needed": plan.spending_changes_needed,
        "decision_explanation": explanation,
    }
    return row


def _analysis_stub(request: dict):
    from orchestration.query_analyser import QueryAnalysis

    return QueryAnalysis(
        intent=request.get("request_text", "")[:200],
        request_type=request.get("request_type", "other"),
        required_data=["financial_profiles", "financial_events", "request_payment_options", "messages", "images"],
        implied_joins=["user_id", "request_id", "related_event_id"],
        expected_output=OUTPUT_COLUMNS,
        constraints=["minimum_balance_to_keep", "desired_completion_date", "home_currency"],
        needs_image=False,
    )


def write_output(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    global QUIET
    parser = argparse.ArgumentParser(description="Buy or Wait? financial agent")
    parser.add_argument("--limit", type=int, help="process only the first N requests")
    parser.add_argument("--request-id", help="process a single request_id")
    parser.add_argument("--sample", action="store_true", help="run the 25 public sample requests")
    parser.add_argument("--skip-agents", action="store_true", help="deterministic engine only (no LLM)")
    parser.add_argument("--out", default=str(SETTINGS.root_output_csv), help="output CSV path")
    parser.add_argument("--quiet", action="store_true", help="suppress step-by-step progress logs")
    args = parser.parse_args(argv)

    QUIET = args.quiet
    use_agents = not args.skip_agents
    requests = _load_requests(args.limit, args.request_id, args.sample)
    source = "sample_requests.csv" if args.sample else "requests.csv"
    log_step(None, None, "Start", f"source={source} requests={len(requests)} agents={'on' if use_agents else 'off'}")

    rows = []
    for i, request in enumerate(requests, 1):
        request_id = request["request_id"]
        user_id = request["user_id"]
        log_step(request_id, user_id, "Request", f"start ({i}/{len(requests)})")
        row = build_row(request, use_agents)
        errors = validation.validate_row(row, request)
        if errors:
            print(f"  [!] {request_id} validation: {errors}", file=sys.stderr)
            log_step(request_id, user_id, "Validation", "failed invariants")
        else:
            log_step(request_id, user_id, "Validation", "passed")
        rows.append(row)
        log_step(request_id, user_id, "Request", f"done -> {row['recommended_payment_method']} / {row['affordability_status']}")

    write_output(rows, Path(args.out))
    TRACKER.write_report(len(rows))
    log_step(None, None, "Output", f"wrote {len(rows)} rows -> {args.out}")
    log_step(None, None, "Output", f"usage report -> {SETTINGS.usage_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
