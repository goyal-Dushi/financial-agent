"""Token/cost accounting collected across all agent runs.

Accumulates usage per agent+model from the openai-agents RunResult.usage object
and renders code/evaluation/usage_report.md.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from config import SETTINGS


@dataclass
class ModelUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0


@dataclass
class UsageTracker:
    per_model: dict[str, ModelUsage] = field(default_factory=lambda: defaultdict(ModelUsage))

    def record(self, model_name: str, usage) -> None:
        if usage is None:
            return
        m = self.per_model[model_name or "unknown"]
        m.calls += 1
        m.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        m.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)

    def record_request(self, model_name: str) -> None:
        self.per_model[model_name or "unknown"].requests += 1

    def write_report(self, n_requests: int) -> None:
        path = SETTINGS.usage_report
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Token Usage and Cost Analysis",
            "",
            f"Final full-dataset run: **{n_requests} requests** processed.",
            "",
            "| Provider | Model | Calls | Input tokens | Output tokens | Total tokens |",
            "|---|---|---:|---:|---:|---:|",
        ]
        tot_in = tot_out = tot_calls = 0
        for model, u in sorted(self.per_model.items()):
            provider = model.split("/")[0] if "/" in model else "openrouter"
            tin, tout = u.input_tokens, u.output_tokens
            tot_in += tin
            tot_out += tout
            tot_calls += u.calls
            lines.append(f"| {provider} | {model} | {u.calls} | {tin} | {tout} | {tin + tout} |")
        lines += [
            f"| **overall** | | **{tot_calls}** | **{tot_in}** | **{tot_out}** | **{tot_in + tot_out}** |",
            "",
        ]
        if n_requests:
            lines += [
                f"- Average tokens per request: **{(tot_in + tot_out) // n_requests}**",
                f"- Average input tokens per request: **{tot_in // n_requests}**",
                f"- Average output tokens per request: **{tot_out // n_requests}**",
                "",
                "Estimated cost depends on the OpenRouter pricing of the configured model(s);",
                "input/output token totals above can be multiplied by the per-model rates.",
            ]
        path.write_text("\n".join(lines) + "\n")


TRACKER = UsageTracker()
