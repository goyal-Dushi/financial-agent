"""DuckDB access layer over the participant dataset (read-only).

Exposes helpers to run SQL against the CSVs and to load the tables the
deterministic engine needs. Never writes to the dataset.
"""

from __future__ import annotations

import duckdb

from config import SETTINGS

TABLES = {
    "requests": "requests.csv",
    "financial_profiles": "financial_profiles.csv",
    "financial_events": "financial_events.csv",
    "exchange_rates": "exchange_rates.csv",
    "request_payment_options": "request_payment_options.csv",
    "messages": "messages.csv",
    "images": "images.csv",
}

_conn: duckdb.DuckDBPyConnection | None = None


def conn() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        _conn = duckdb.connect()
    return _conn


def _path(filename: str) -> str:
    return str(SETTINGS.dataset_dir / filename)


def register_views() -> None:
    c = conn()
    for view, filename in TABLES.items():
        c.execute(
            f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM read_csv_auto('{_path(filename)}', header=true)"
        )


def run_sql(sql: str) -> list[dict]:
    """Execute a SELECT and return rows as dicts."""
    register_views()
    rel = conn().execute(sql)
    cols = [d[0] for d in rel.description]
    return [dict(zip(cols, row)) for row in rel.fetchall()]


def load_all_users() -> list[dict]:
    return run_sql("SELECT * FROM requests ORDER BY request_id")
