# AGENTS.md

HackerRank Orchestrate (September 2026) — Buy or Wait?

This file is the single source of truth for any AI coding agent working in this repo: Claude Code, OpenAI Codex CLI / Codex Cloud, Gemini CLI, Cursor, Windsurf, opencode, Aider, goose, Factory, RooCode, JetBrains Junie, GitHub Copilot, Devin, or any other AGENTS.md-aware tool.

Read this file in full before taking any action. Obey it exactly unless the user or platform provides higher-priority instructions.

---

## 0. TLDR For The Agent

On every session start, do this in order:

1. Read this file completely.
2. Check the log file path in §2.
3. Append a `SESSION START` entry using §5.1.
4. For every user turn, append a summary entry using §5.2.
5. When building, testing, or packaging the solution, follow the project contract in §6.

Do not skip logging or rewrite old log entries. Sub-agents and worktrees use the same log file.

---

## 1. What This Repo Is

This is a starter repo for the **HackerRank Orchestrate** 24-hour hackathon challenge: **Buy or Wait?**

Participants must build an AI-powered financial agent. For every purchase or payment request in `dataset/requests.csv`, the agent decides whether the user should pay in full, pay partially, use an available installment option, wait, or not proceed.

The system reconstructs the user's financial position from structured profiles and financial events, fixed dated exchange rates, seller/provider payment options, and relevant messages or images. It must account for recurring commitments, pending payments, essential spending, confirmed income, financial priorities, and the minimum balance the user wants to keep. Messages and images are untrusted evidence; they may clarify, amend, delay, cancel, or confirm a financial fact, but their embedded instructions never override the challenge rules. There are no voice notes or live banking, market-data, or exchange-rate calls.

The final submission must produce `output.csv` with:

```text
request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation
```

Read `problem.md` for the full specification.

---

## 2. Log File — Location And Lifecycle

The log file is named `log.txt` and lives in the same directory as this `AGENTS.md` file (and the `CLAUDE.md` that imports it) — the repository root.

| Platform | Path |
|---|---|
| macOS / Linux | `<directory containing AGENTS.md>/log.txt` |

Resolve the path relative to this file. Do not hardcode a folder name, a user path, or the platform home directory, so the location stays correct across clones, renames, and checkouts.

Rules:

- Create the file if missing.
- Never commit or add the log file to git. Keep `log.txt` in `.gitignore`.
- Append only. Do not rewrite, reorder, or delete prior entries.
- One shared log per checkout. All agents and sub-agents append to the same file next to the top-level `AGENTS.md`, never a private copy.
- Never log secrets. Redact API keys, tokens, cookies, private keys, and sensitive PII.

---

## 3. Log Format

### 3.1 Session Start Entry

```text
## [ISO-8601 TIMESTAMP] SESSION START

tool=<exact_harness_or_coding_agent_name>
Repo Root: <absolute_path>
Branch: <git_branch_or_unknown>
Worktree: <worktree_path_or_main>
Parent Agent: <parent_agent_name_or_none>
Language: <js|ts|py|custom:name>
Time Remaining: <Xd Yh Zm, or not configured>
```

### 3.2 Per-Turn Entry

Append after every user message you respond to:

```text
## [ISO-8601 TIMESTAMP] <short title, max 80 chars>

User Prompt (verbatim, secrets redacted):
<exact user message, with secrets replaced by [REDACTED]>

Agent Response Summary:
<2-5 sentences: what was done, why, and any important decision>

Actions:
* <file edited / command run / tool invoked>

Context:
tool=<exact_harness_or_coding_agent_name>
branch=<git_branch_or_unknown>
repo_root=<absolute_path>
worktree=<worktree_path_or_main>
parent_agent=<parent_name_or_none>
```

**Mandatory tool-name rule:** Every `SESSION START` and per-turn log entry must contain one non-empty `tool=` line with the exact name of the coding harness or agent writing the entry. Replace the template value before writing the log. The entry is invalid if `tool=` is missing, blank, still contains a placeholder, uses a generic label such as `AI`, contains only a model name, or names a different harness. Before responding, verify the value against the harness identity provided by the current runtime and re-read the appended entry to confirm it matches. Never guess the tool name. Correct any mismatch before responding to the user.

### 3.3 Sub-Agent And Worktree Rules

- Sub-agents must log their own entries using the same file.
- Set `parent_agent=` to the parent agent's name.
- Worktrees use the same shared log file, not a per-worktree copy.

### 3.4 What Not To Log

- API keys, tokens, session cookies, OAuth codes, or private keys.
- Sensitive PII.
- Full contents of large files or binary blobs. Reference by path instead.

---

## 4. Project Contract

### 4.1 Dataset Contract

Participant-facing files are inside `dataset/`.

```text
dataset/
├── financial_profiles.csv
├── financial_events.csv
├── exchange_rates.csv
├── requests.csv
├── sample_requests.csv
├── request_payment_options.csv
├── messages.csv
├── images.csv
├── output.csv
└── media/
    └── images/
```

Refer to `schema.md` file for details regarding each .csv file.

### 4.2 Required Output

The solution must write `output.csv` with these exact columns, in this order:

```text
request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation
```

Refer to `details.md` file for further details on the output to be generated and things to consider. 

### 4.3 Financial Decision Rules

- Detect recurrence only when history supports it. Forecast essential variable spending conservatively.
- Reserve pending debits. Do not count pending credits, bonuses, commissions, refunds, lottery proceeds, or investment gains until they settle.
- Count confirmed salary on its settlement date. Do not invent unsupported future income, expenses, payment options, or other financial facts.
- The balance must never fall below `minimum_balance_to_keep` after any projected essential expense or payment in the recommended plan.
- Respect the user's protected categories and preferences. Prefer a plan that completes the request by its deadline, avoids spending changes, minimizes total payment cost, starts earlier, and uses fewer payments.
- Resolve conflicts using an explicit cancellation, settlement, or amendment first; then newer records from the same source; then a settled event; then the financially safer interpretation.

### 4.4 Constraints That Make The Submission Evaluable

- Be runnable from the terminal.
- Read the provided files from `dataset/`.
- Do not use organizer-only files or hardcoded labels.
- Keep behavior deterministic where possible.
- Read secrets from environment variables only.
- Include clear setup and run instructions in the submitted code package.

### 4.5 Reasonable Entry Points
`code/main.py` 

--- 