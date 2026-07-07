"""Central configuration: model casting, thresholds, sampling cadence.

Design principle #1: LLMs argue and explain; deterministic code measures and
extrapolates. Every number the system acts on is produced by code in this
package, never by a model. The thresholds that drive verdicts live here so
they are auditable in one place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Model casting (spec section 8). Seat -> model id on the serving endpoint.
# In mock mode these are labels only; in live mode they are passed as the
# `model` field of the OpenAI-compatible request. Defaults are Fireworks
# serverless ids; override per seat with DRIFT_MODEL_<SEAT> (e.g. a plain
# "qwen3-30b-a3b" on a self-hosted vLLM/ROCm endpoint).
# ---------------------------------------------------------------------------
_DEFAULT_CASTING = {
    "scorer": "accounts/fireworks/models/qwen3-30b-a3b",
    "prosecutor": "accounts/fireworks/models/qwen3-30b-a3b",
    "defense": "accounts/fireworks/models/qwen3-30b-a3b",
    "judge": "accounts/fireworks/models/qwen3-235b-a22b-instruct-2507",
    "voice": "accounts/fireworks/models/qwen3-30b-a3b",
}
MODEL_CASTING: dict[str, str] = {
    seat: os.environ.get(f"DRIFT_MODEL_{seat.upper()}", default)
    for seat, default in _DEFAULT_CASTING.items()
}

# Seats whose output contract is short and structured; on hybrid Qwen3 models
# (thinking switchable per-message) these get the /no_think soft switch so the
# high-volume seats don't pay 10-20x tokens for reasoning they don't need.
# The judge is exempt: if cast as a thinking model, let it think.
NO_THINK_SEATS = frozenset({"scorer", "prosecutor", "defense", "voice"})

# ---------------------------------------------------------------------------
# Quality + court thresholds
# ---------------------------------------------------------------------------
QUALITY_FLOOR = 0.60  # scores are 0..1; below this a response is "unacceptable"

WINDOW_SIZE = 80  # rows per hearing window
MIN_SAMPLE = 30  # Defense wins automatically below this (sample_size confounder)

HEARING_EVERY = 40  # rows between hearings in the calm state
HEARING_EVERY_WATCH = 15  # tightened sampling after a WATCH ruling

# Trend significance gates used by court.stats / the deterministic judge rule.
TREND_P_ALERT = 0.01  # p-value the Prosecutor's trend must beat for ALERT
TREND_P_WATCH = 0.10  # weaker evidence -> WATCH (buy evidence, not silence)
TREND_R2_ALERT = 0.25  # minimum fit quality for ALERT

# Forecaster refuses to emit a countdown below this fit quality; a range is
# honest, a confident single number from a bad fit is theater.
FORECAST_MIN_R2 = 0.30


@dataclass(frozen=True)
class Settings:
    llm_mode: str
    llm_base_url: str
    llm_api_key: str
    database_url: str
    webhook_url: str


def settings() -> Settings:
    return Settings(
        llm_mode=os.environ.get("DRIFT_LLM_MODE", "mock").lower(),
        llm_base_url=os.environ.get(
            "DRIFT_LLM_BASE_URL", "https://api.fireworks.ai/inference/v1"
        ),
        llm_api_key=os.environ.get("DRIFT_LLM_API_KEY", ""),
        database_url=os.environ.get("DATABASE_URL", "sqlite:///drift.db"),
        webhook_url=os.environ.get("DRIFT_WEBHOOK_URL", ""),
    )
