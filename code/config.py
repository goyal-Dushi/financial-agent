"""Central configuration: loads .env, resolves per-agent models and paths.

All secrets come from the environment (never hardcoded). Provides a single
factory to build a LitellmModel for any agent with optional per-agent override.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# code/ is the working directory of this package; repo root is one level up.
CODE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CODE_DIR.parent

# Load secrets from the environment only. Prefer a .env at the repo root (the
# conventional location for this challenge) and fall back to code/.env. Existing
# environment variables always win because load_dotenv does not override by default.
for _env_file in (REPO_ROOT / ".env", CODE_DIR / ".env"):
    if _env_file.exists():
        load_dotenv(_env_file)
        break


def _env(name: str, default: str = "") -> str:
    val = os.environ.get(name, default)
    return val.strip() if val else default


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    default_model: str
    temperature: float
    dataset_dir: Path
    code_output_dir: Path
    cache_dir: Path
    output_csv: Path
    usage_report: Path
    site_url: str
    app_name: str

    def model_for(self, agent_env_key: str) -> str:
        """Return per-agent model if set, else the shared default."""
        return _env(agent_env_key) or self.default_model

    def openrouter_headers(self) -> dict[str, str]:
        headers = {}
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.app_name:
            headers["X-Title"] = self.app_name
        return headers

    def model_settings(self):
        from agents import ModelSettings

        return ModelSettings(temperature=self.temperature, tool_choice="auto")


def _resolve_path(raw: str, fallback: Path) -> Path:
    if not raw:
        return fallback
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def load_settings() -> Settings:
    dataset_dir = _resolve_path(_env("DATASET_DIR"), REPO_ROOT / "dataset")
    code_output_dir = _resolve_path(_env("OUTPUT_DIR"), CODE_DIR / "output")
    cache_dir = _resolve_path(_env("CACHE_DIR"), CODE_DIR / "cache")
    output_csv = _resolve_path(_env("OUTPUT_CSV"), CODE_DIR / "output.csv")
    usage_report = _resolve_path(_env("USAGE_REPORT"), CODE_DIR / "evaluation" / "usage_report.md")
    temperature = float(_env("LLM_TEMPERATURE") or "0")

    return Settings(
        api_key=_env("OPENROUTER_API_KEY"),
        base_url=_env("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1",
        default_model=_env("OPENROUTER_MODEL"),
        temperature=temperature,
        dataset_dir=dataset_dir,
        code_output_dir=code_output_dir,
        cache_dir=cache_dir,
        output_csv=output_csv,
        usage_report=usage_report,
        site_url=_env("OPENROUTER_SITE_URL"),
        app_name=_env("OPENROUTER_APP_NAME"),
    )


SETTINGS = load_settings()

# Per-agent env keys (may be blank to fall back to OPENROUTER_MODEL).
MODEL_ENV_KEYS = {
    "query_analyser": "QUERY_ANALYSER_MODEL",
    "data_generator": "DATA_GENERATOR_MODEL",
    "vision_ocr": "VISION_MODEL",
    "image_tabularizer": "IMAGE_TABULARIZER_MODEL",
    "aggregator": "AGGREGATOR_MODEL",
}


def build_model(agent_name: str):
    """Build a LitellmModel for the given agent using its resolved OpenRouter model."""
    from agents.extensions.models.litellm_model import LitellmModel

    model_id = SETTINGS.model_for(MODEL_ENV_KEYS[agent_name])
    if not model_id:
        raise RuntimeError(
            f"No model configured for agent '{agent_name}'. Set {MODEL_ENV_KEYS[agent_name]} "
            "or OPENROUTER_MODEL in the environment."
        )
    if not SETTINGS.api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set in the environment.")
    full_model = model_id if model_id.startswith("openrouter/") else f"openrouter/{model_id}"
    return LitellmModel(
        model=full_model,
        api_key=SETTINGS.api_key,
        base_url=SETTINGS.base_url,
    )
