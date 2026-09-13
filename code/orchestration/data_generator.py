"""Agent 2 — Data Generator (tool-using).

Given the QueryAnalysis, it assembles the concrete data the engine needs: it reads the
per-agent query cache, issues duckdb SQL via a tool when something is missing, saves the
result CSV under code/output/{user_id}/, updates the cache, and (when the analysis flags
needs_image) delegates to the Vision/OCR agent to pull amounts from images.

The returned DataDossier is what the Aggregator consumes.
"""

from __future__ import annotations

import csv
import io
import json

from pydantic import BaseModel, Field

from agents import Agent, Runner, function_tool

from config import SETTINGS, build_model
from orchestration import query_analyser, vision_ocr_agent
from tools import cache, db
from tools.usage import TRACKER


class DataDossier(BaseModel):
    request_id: str
    files_written: list[str] = Field(default_factory=list)
    notes: str = ""


_SAFE_PREFIX = ("SELECT", "WITH", "COPY (SELECT", "COPY (WITH")


def _make_tools(user_id: str, request_id: str):
    @function_tool(name_override="run_sql", description_override="Run a read-only duckdb SELECT against the dataset views (requests, financial_profiles, financial_events, exchange_rates, request_payment_options, messages, images). Returns CSV text.")
    def run_sql(sql: str) -> str:
        s = sql.strip().upper()
        if not s.startswith(_SAFE_PREFIX):
            return "ERROR: only SELECT/WITH/COPY(SELECT) queries are allowed."
        rows = db.run_sql(sql)
        if not rows:
            return ""
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
        return buf.getvalue()

    @function_tool(name_override="write_user_csv", description_override="Save CSV content for this user's data extract under code/output/{user_id}/<name>.csv")
    def write_user_csv(name: str, content: str) -> str:
        out_dir = SETTINGS.code_output_dir / user_id
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{name}.csv"
        p.write_text(content)
        return str(p)

    @function_tool(name_override="read_payment_image", description_override="Extract financial facts (amounts, pay slips, receipts) from the user's supporting images. RapidOCR reads the raw text locally, then the facts are returned as text.")
    def read_payment_image() -> str:
        result = vision_ocr_agent.read_images_for(user_id, request_id)
        return result.text or "No financial text found in the linked images."

    return [run_sql, write_user_csv, read_payment_image]


def build_agent(user_id: str, request_id: str) -> Agent:
    tools = _make_tools(user_id, request_id)
    return Agent(
        name="data_generator",
        instructions=(
            "You are the Data Generator. Given a query analysis for one Buy-or-Wait "
            "request, gather the underlying financial data using the SQL tools and write "
            "per-user CSV extracts. Consult the cache first and only run new SQL for gaps. "
            "When image evidence is required (needs_image true, or a blank event amount), "
            "call the read_payment_image tool. Keep outputs faithful to the dataset; never "
            "fabricate rows."
        ),
        model=build_model("data_generator"),
        model_settings=SETTINGS.model_settings(),
        tools=tools,
        output_type=DataDossier,
    )


def generate(analysis: query_analyser.QueryAnalysis, user_id: str, request_id: str) -> DataDossier:
    cached = cache.lookup("data_generator", request_id)
    if cached:
        try:
            data = json.loads(cached)
            return DataDossier(**data)
        except Exception:
            pass
    prompt = (
        f"Request {request_id} for {user_id}. Analysis:\n"
        f"intent: {analysis.intent}\nrequired_data: {analysis.required_data}\n"
        f"joins: {analysis.implied_joins}\nneeds_image: {analysis.needs_image}\n"
        "Write the per-user extracts needed for the decision and return the dossier."
    )
    result = Runner.run_sync(build_agent(user_id, request_id), prompt)
    if result.raw_responses:
        TRACKER.record(SETTINGS.model_for("data_generator"), result.raw_responses[-1].usage)
    dossier = result.final_output
    cache.upsert("data_generator", request_id, json.dumps(dossier.model_dump()))
    return dossier
