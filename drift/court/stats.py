"""Deterministic trend statistics. No LLM produces or touches these numbers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

import numpy as np
import ruptures as rpt
from scipy import stats as sps


@dataclass(frozen=True)
class TrendFit:
    n: int
    slope_per_hour: float
    intercept: float
    r2: float
    p_value: float
    stderr: float
    duration_hours: float
    end_value: float  # fitted value at the window's end

    def to_dict(self) -> dict:
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def _hours(rows: list[dict]) -> np.ndarray:
    t0: datetime = rows[0]["ts"]
    return np.array([(r["ts"] - t0).total_seconds() / 3600.0 for r in rows])


def feature_series(rows: list[dict], feature: str = "quality") -> np.ndarray:
    return np.array([float(r["features"].get(feature, 0.0)) for r in rows])


def fit_trend(rows: list[dict], feature: str = "quality") -> TrendFit | None:
    """Least-squares linear trend of a feature over wall-clock time."""
    if len(rows) < 3:
        return None
    x = _hours(rows)
    y = feature_series(rows, feature)
    if float(x[-1] - x[0]) <= 0:
        return None
    res = sps.linregress(x, y)
    return TrendFit(
        n=len(rows),
        slope_per_hour=float(res.slope),
        intercept=float(res.intercept),
        r2=float(res.rvalue**2),
        p_value=float(res.pvalue),
        stderr=float(res.stderr),
        duration_hours=float(x[-1] - x[0]),
        end_value=float(res.intercept + res.slope * x[-1]),
    )


def residual_std(rows: list[dict], fit: TrendFit, feature: str = "quality") -> float:
    x = _hours(rows)
    y = feature_series(rows, feature)
    resid = y - (fit.intercept + fit.slope_per_hour * x)
    return float(np.std(resid))


def changepoint_index(rows: list[dict], feature: str = "quality", min_size: int = 15) -> int | None:
    """Most likely single changepoint in the series (ruptures PELT, rbf cost)."""
    y = feature_series(rows, feature)
    if len(y) < 2 * min_size:
        return None
    algo = rpt.Pelt(model="rbf", min_size=min_size).fit(y.reshape(-1, 1))
    breaks = algo.predict(pen=5)
    # last element is always len(y); interior breaks are candidate changepoints
    interior = [b for b in breaks if b < len(y)]
    return interior[0] if interior else None


def project_hours_to_floor(fit: TrendFit, floor: float) -> float | None:
    """Hours from the window's end until the fitted trend crosses the floor.

    None when the trend is flat/improving or the fit is already below floor
    is reported as 0.0 (crossing already happened per the fit).
    """
    if fit.slope_per_hour >= -1e-9:
        return None
    if fit.end_value <= floor:
        return 0.0
    return (floor - fit.end_value) / fit.slope_per_hour
