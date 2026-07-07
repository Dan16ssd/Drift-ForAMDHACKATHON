"""The Defense's checklist — deterministic tests for every innocent explanation
of an apparent quality decline. Each check returns a finding; the Defense
argues from findings, it does not invent them.

The critical check is traffic_mix_shift: a stream whose hard-question share
grows shows a falling aggregate mean with zero real degradation. Pure
changepoint detection convicts that stream; this check acquits it by testing
whether any within-segment trend actually declines.
"""

from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np
from scipy import stats as sps

from drift.config import MIN_SAMPLE
from drift.court.stats import TrendFit, feature_series, fit_trend, residual_std


def _finding(name: str, fired: bool, detail: str, stat: float | None = None) -> dict:
    return {"name": name, "fired": fired, "detail": detail, "stat": stat}


def check_sample_size(rows: list[dict]) -> dict:
    n = len(rows)
    return _finding(
        "sample_size",
        n < MIN_SAMPLE,
        f"window has {n} rows (minimum for a conviction: {MIN_SAMPLE})",
        float(n),
    )


def _segment_trends(rows: list[dict], key: str) -> dict[str, TrendFit | None]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["features"].get(key, "?")].append(r)
    return {g: fit_trend(members) for g, members in groups.items() if len(members) >= 10}


def check_traffic_mix_shift(rows: list[dict], aggregate: TrendFit | None) -> dict:
    """Fires when the composition of traffic changed AND no segment actually
    degrades — i.e. the aggregate decline is a mix artifact."""
    if len(rows) < 20:
        return _finding("traffic_mix_shift", False, "window too small to test mix", None)
    half = len(rows) // 2
    first, second = rows[:half], rows[half:]
    cats = sorted({r["features"].get("difficulty", "?") for r in rows})
    if len(cats) < 2:
        return _finding("traffic_mix_shift", False, "single traffic segment", None)
    c1 = Counter(r["features"].get("difficulty", "?") for r in first)
    c2 = Counter(r["features"].get("difficulty", "?") for r in second)
    table = np.array([[c1.get(c, 0) for c in cats], [c2.get(c, 0) for c in cats]])
    if (table.sum(axis=0) == 0).any():
        return _finding("traffic_mix_shift", False, "degenerate contingency table", None)
    chi2, p, _, _ = sps.chi2_contingency(table)

    seg = _segment_trends(rows, "difficulty")
    declining = [
        g
        for g, f in seg.items()
        if f is not None and f.slope_per_hour < 0 and f.p_value < 0.05
    ]
    mix_shifted = p < 0.05
    fired = bool(
        mix_shifted
        and not declining
        and aggregate is not None
        and aggregate.slope_per_hour < 0
    )
    shares = {c: f"{c1.get(c, 0)}->{c2.get(c, 0)}" for c in cats}
    detail = (
        f"traffic mix chi2 p={p:.4g} (shares first->second half: {shares}); "
        f"segments with significant decline: {declining or 'none'}"
    )
    return _finding("traffic_mix_shift", fired, detail, float(p))


def check_outlier_user(rows: list[dict]) -> dict:
    n = len(rows)
    if n < 10:
        return _finding("outlier_user", False, "window too small", None)
    counts = Counter(r["features"].get("user_id", "?") for r in rows)
    user, k = counts.most_common(1)[0]
    share = k / n
    if share <= 0.30:
        return _finding("outlier_user", False, f"largest user share {share:.0%} ({user})", share)
    theirs = [float(r["features"]["quality"]) for r in rows if r["features"].get("user_id") == user]
    others = [float(r["features"]["quality"]) for r in rows if r["features"].get("user_id") != user]
    gap = abs(float(np.mean(theirs)) - float(np.mean(others))) if others else 0.0
    fired = share > 0.30 and gap > 0.15
    return _finding(
        "outlier_user",
        fired,
        f"user {user} is {share:.0%} of window; quality gap vs rest {gap:.2f}",
        share,
    )


def check_time_of_day(rows: list[dict]) -> dict:
    """Only attributable when the window covers multiple days; a single-day
    window cannot distinguish a daily cycle from a genuine monotonic trend."""
    dates = {r["ts"].date() for r in rows}
    if len(dates) < 2:
        return _finding(
            "time_of_day",
            False,
            "window covers a single day; daily-cycle attribution not possible",
            None,
        )
    hours = np.array([r["ts"].hour + r["ts"].minute / 60.0 for r in rows])
    quality = feature_series(rows)
    if np.std(hours) < 1e-9:
        return _finding("time_of_day", False, "no hour variation", None)
    r, p = sps.pearsonr(hours, quality)
    fired = bool(abs(r) > 0.5 and p < 0.01)
    return _finding("time_of_day", fired, f"hour-of-day correlation r={r:.2f} p={p:.4g}", float(r))


def check_scorer_noise(rows: list[dict], aggregate: TrendFit | None) -> dict:
    if aggregate is None:
        return _finding("scorer_noise", False, "no trend fitted", None)
    total_decline = abs(aggregate.slope_per_hour * aggregate.duration_hours)
    noise = residual_std(rows, aggregate)
    fired = bool(aggregate.slope_per_hour < 0 and total_decline < 1.5 * noise)
    return _finding(
        "scorer_noise",
        fired,
        f"projected decline over window {total_decline:.3f} vs residual std {noise:.3f} "
        f"(fires when decline < 1.5x noise)",
        float(total_decline / noise) if noise > 0 else None,
    )


def run_checklist(rows: list[dict], aggregate: TrendFit | None) -> list[dict]:
    return [
        check_sample_size(rows),
        check_traffic_mix_shift(rows, aggregate),
        check_outlier_user(rows),
        check_time_of_day(rows),
        check_scorer_noise(rows, aggregate),
    ]
