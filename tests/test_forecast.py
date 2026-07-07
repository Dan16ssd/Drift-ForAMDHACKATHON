from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from drift.forecast.countdown import attribute_cause, compute_countdown


def rows_with(features_fn, n=80, minutes_apart=10.0):
    t0 = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    return [
        {"id": i + 1, "ts": t0 + timedelta(minutes=i * minutes_apart), "features": features_fn(i)}
        for i in range(n)
    ]


def test_countdown_on_clean_decline():
    # quality falls 0.03/h from 0.9; floor 0.6 -> ends ~0.9-0.03*13.2h = 0.5
    rows = rows_with(lambda i: {"quality": 0.9 - 0.005 * i})
    cd = compute_countdown(rows, "s1", floor=0.45)
    assert cd is not None
    # analytic: end value ~0.505, slope -0.03/h -> ~1.8h
    assert cd.hours_best == pytest.approx(1.8, abs=0.4)
    assert cd.hours_low <= cd.hours_best
    assert cd.hours_high is None or cd.hours_high >= cd.hours_best


def test_countdown_refuses_weak_fit():
    import random

    rng = random.Random(1)
    rows = rows_with(lambda i: {"quality": 0.8 + rng.uniform(-0.1, 0.1)})
    assert compute_countdown(rows, "s1") is None


def test_countdown_refuses_improving_stream():
    rows = rows_with(lambda i: {"quality": 0.6 + 0.003 * i})
    assert compute_countdown(rows, "s1") is None


def test_cause_attribution_retrieval_decay():
    rows = rows_with(
        lambda i: {
            "quality": 0.9 - 0.004 * i,
            "retrieval_hit_ratio": 1.0 - 0.008 * i,
            "adherence": 0.9,
            "latency_ms": 1200.0,
            "refusal": 0.0,
            "hedge_rate": 0.0,
        }
    )
    cause, evidence = attribute_cause(rows)
    assert cause == "retrieval decay"
    assert "retrieval_hit_ratio" in evidence
