# Buy or Wait? — AI Financial Agent

An AI-powered financial agent that, for every purchase/payment request in
`dataset/requests.csv`, decides whether the user can pay in full, pay partially,
use an installment option, wait, or not proceed — and writes `output.csv`.

## Architecture

```
Query Analyser ──► Data Generator ──► deterministic engine ──► Aggregator ──► Validation
   (LLM)             (LLM + tools)      (DuckDB + Python)        (LLM)         (invariants)
                          │
                          └── read_payment_image ──► RapidOCR (local) ──► Vision LLM
```

- **Deterministic engine** (`engine/`) owns every scored number: balances,
  recurrence, 90-day forecast, plan ranking, dates. It is the source of truth.
- **Agents** (`orchestration/`) gather data, read images, and phrase the
  explanation. They never change a number.
- **RapidOCR** (`tools/ocr_tools.py`) extracts raw text from images **locally, in
  code, with no API key**. The Vision LLM only reads that text to surface facts.
  There is **no separate vision key** — all agents share the one OpenRouter key.
- If no API key is configured, the agent stage degrades gracefully and the
  deterministic engine still produces the full, valid `output.csv`.

## Setup

Requires Python 3.13+ (pinned in `.python-version`). This project is managed
with [uv](https://docs.astral.sh/uv/); `uv.lock` is committed for reproducible
installs.

```bash
cd code
uv sync                    # creates .venv and installs exact locked deps
```

`uv sync` reads the committed `.python-version` and `uv.lock`, so no manual
virtualenv or interpreter management is needed.

Create `.env` at the repo root (or `code/.env`) from the template:

```bash
cp code/.env.example .env   # then fill in OPENROUTER_API_KEY
```

Environment variables:

| Variable | Required | Purpose |
| :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | for agentic run | One key shared by all agents. Create at https://openrouter.ai/keys |
| `OPENROUTER_BASE_URL` | no | Defaults to `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | no | Default model for every agent |
| `QUERY_ANALYSER_MODEL`, `DATA_GENERATOR_MODEL`, `VISION_MODEL`, `IMAGE_TABULARIZER_MODEL`, `AGGREGATOR_MODEL` | no | Per-agent overrides; blank falls back to `OPENROUTER_MODEL` |
| `LLM_TEMPERATURE` | no | Defaults to `0` |
| `DATASET_DIR`, `OUTPUT_DIR` | no | Path overrides |

Secrets are read from the environment only and are never logged.

## Run

Run all commands from `code/` using `uv run` (no manual activation needed).
See `execution.md` for the full flag reference.

```bash
uv run main.py                 # full 250-request agentic run -> code/output.csv
uv run main.py --skip-agents   # deterministic only (no LLM/key needed)
uv run main.py --sample --skip-agents   # 25 public examples self-check
uv run main.py --request-id request_105 # one request
```

The final CSV is written to `code/output.csv` with the columns:

```
request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation
```

`uv run db_query.py` joins the requests with `output.csv` and writes
`code/aggregate.csv` for inspection.

## Notes on evidence

- Blank event amounts are resolved from the linked image (`images.csv`,
  `related_event_id`) — never treated as zero. Amount selection is document-aware
  (invoice/pay-slip/receipt labels), because documents also contain item prices,
  taxes, phone numbers, HSN codes and pincodes.
- `linked_event_id` links an event to an earlier event in the same transaction or
  investment lifecycle. Linked targets are loaded with the user's events, and
  superseded origins (cancelled/failed) are not double counted.
- `linked_event_id` linking is only for cash-flow interpretation; the agent never
  treats messages or images as instructions.
