"""Deterministic countdown: hours until quality crosses the floor.

Pure regression math — an LLM never computes these numbers. The range comes
from the slope's 95% confidence interval; when the fit is too weak to support
any number (R² below FORECAST_MIN_R2), no countdown is emitted at all: a range
is honest, a confident number from a bad fit is theater.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from drift.config import FORECAST_MIN_R2, QUALITY_FLOOR
from drift.court.stats import fit_trend, project_hours_to_floor

# Feature channels examined for cause attribution: (feature, direction that is
# abnormal, human-readable cause).
CAUSE_CHANNELS = [
    ("retrieval_hit_ratio", -1, "retrieval decay"),
    ("refusal", +1, "rising refusal rate"),
    ("latency_ms", +1, "latency regression"),
    ("hedge_rate", +1, "rising hedging"),
    ("adherence", -1, "instruction-adherence loss"),
]


@dataclass
class Countdown:
    stream_id: str
    as_of: str
    hours_low: float  # sooner bound (steeper slope in the CI)
    hours_best: float
    hours_high: float | None  # None = shallow bound of the CI never crosses
    r2: float
    slope_per_hour: float
    n: int
    floor: float
    probable_cause: str
    cause_evidence: str

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("hours_low", "hours_best", "hours_high", "r2", "slope_per_hour"):
            if d[k] is not None:
                d[k] = round(d[k], 2)
        return d


def attribute_cause(rows: list[dict]) -> tuple[str, str]:
    """Which sensor channel moved abnormally, and in the right direction?"""
    candidates = []
    for feature, direction, cause in CAUSE_CHANNELS:
        fit = fit_trend(rows, feature)
        if fit is None:
            continue
        if fit.slope_per_hour * direction > 0 and fit.p_value < 0.05:
            candidates.append((fit.p_value, cause, feature, fit))
    if not candidates:
        return "unattributed decline", "no single sensor channel moved significantly"
    candidates.sort()
    _, cause, feature, fit = candidates[0]
    evidence = f"{feature} trending {fit.slope_per_hour:+.4f}/h (p={fit.p_value:.3g})"
    stable = [
        f
        for f, d, _ in CAUSE_CHANNELS
        if f != feature
        and ((g := fit_trend(rows, f)) is None or g.p_value > 0.2)
    ]
    if stable:
        evidence += f"; stable channels: {', '.join(stable)}"
    return cause, evidence


def compute_countdown(
    rows: list[dict], stream_id: str, floor: float = QUALITY_FLOOR
) -> Countdown | None:
    fit = fit_trend(rows)
    if fit is None or fit.slope_per_hour >= 0 or fit.r2 < FORECAST_MIN_R2:
        return None
    best = project_hours_to_floor(fit, floor)
    if best is None:
        return None

    steep = fit.slope_per_hour - 1.96 * fit.stderr
    shallow = fit.slope_per_hour + 1.96 * fit.stderr
    low = (floor - fit.end_value) / steep if steep < 0 else best
    high = (floor - fit.end_value) / shallow if shallow < 0 else None
    if fit.end_value <= floor:
        low, best, high = 0.0, 0.0, 0.0

    cause, cause_evidence = attribute_cause(rows)
    return Countdown(
        stream_id=stream_id,
        as_of=rows[-1]["ts"].isoformat(),
        hours_low=max(0.0, low),
        hours_best=max(0.0, best),
        hours_high=max(0.0, high) if high is not None else None,
        r2=fit.r2,
        slope_per_hour=fit.slope_per_hour,
        n=fit.n,
        floor=floor,
        probable_cause=cause,
        cause_evidence=cause_evidence,
    )
