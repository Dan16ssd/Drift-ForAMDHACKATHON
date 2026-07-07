from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from drift.court.confounders import check_traffic_mix_shift, run_checklist
from drift.court.debate import hold_hearing
from drift.court.rules import deterministic_verdict
from drift.court.stats import fit_trend, project_hours_to_floor
from drift.ledger.store import LedgerStore
from tests.conftest import load_records, sensed_window


def synthetic_rows(qualities: list[float], minutes_apart: float = 10.0) -> list[dict]:
    t0 = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    return [
        {
            "id": i + 1,
            "ts": t0 + timedelta(minutes=i * minutes_apart),
            "features": {"quality": q, "difficulty": "easy", "user_id": f"u{i % 5}"},
        }
        for i, q in enumerate(qualities)
    ]


def test_fit_trend_detects_decline():
    rows = synthetic_rows([0.9 - 0.005 * i for i in range(60)])
    fit = fit_trend(rows)
    assert fit is not None
    assert fit.slope_per_hour < 0
    assert fit.p_value < 1e-6
    assert fit.r2 > 0.95


def test_project_hours_to_floor():
    # 0.9 falling 0.03/hour over 10h -> ends at 0.6... exactly at floor
    rows = synthetic_rows([0.9 - 0.005 * i for i in range(60)])
    fit = fit_trend(rows)
    hours = project_hours_to_floor(fit, floor=0.45)
    # end value ~0.605, slope ~-0.03/h -> ~5.2h to 0.45
    assert hours == pytest.approx(5.2, abs=0.5)


def test_flat_trend_projects_nothing():
    rows = synthetic_rows([0.85] * 40)
    fit = fit_trend(rows)
    assert project_hours_to_floor(fit, floor=0.6) is None


def test_deterministic_verdict_paths():
    alert_ev = {
        "trend": {"slope_per_hour": -0.04, "p_value": 1e-8, "r2": 0.6, "n": 80},
        "confounders": [{"name": "sample_size", "fired": False, "detail": ""}],
    }
    assert deterministic_verdict(alert_ev)[0] == "ALERT"

    dismissed_ev = {
        "trend": {"slope_per_hour": -0.04, "p_value": 1e-8, "r2": 0.6, "n": 80},
        "confounders": [{"name": "traffic_mix_shift", "fired": True, "detail": "mix shifted"}],
    }
    assert deterministic_verdict(dismissed_ev)[0] == "DISMISS"

    watch_ev = {
        "trend": {"slope_per_hour": -0.02, "p_value": 0.05, "r2": 0.1, "n": 80},
        "confounders": [],
    }
    assert deterministic_verdict(watch_ev)[0] == "WATCH"

    healthy_ev = {
        "trend": {"slope_per_hour": 0.001, "p_value": 0.9, "r2": 0.0, "n": 80},
        "confounders": [],
    }
    assert deterministic_verdict(healthy_ev)[0] == "DISMISS"


def test_confounder_stream_full_window_is_the_hard_case(mock_client):
    """The soul of the repo: over the WHOLE confounder stream the aggregate
    trend is significantly negative (pure trend detection convicts), yet the
    traffic-mix check fires and the court acquits."""
    rows = sensed_window(load_records("confounder_stream.jsonl"), mock_client)
    aggregate = fit_trend(rows)
    assert aggregate is not None
    assert aggregate.slope_per_hour < 0
    assert aggregate.p_value < 0.01  # a naive detector would alert here

    finding = check_traffic_mix_shift(rows, aggregate)
    assert finding["fired"], finding["detail"]

    evidence = {"trend": aggregate.to_dict(), "confounders": run_checklist(rows, aggregate)}
    verdict, reasoning = deterministic_verdict(evidence)
    assert verdict == "DISMISS", reasoning


def test_drift_stream_full_window_convicts(mock_client):
    rows = sensed_window(load_records("drift_stream.jsonl"), mock_client)
    aggregate = fit_trend(rows)
    evidence = {"trend": aggregate.to_dict(), "confounders": run_checklist(rows, aggregate)}
    verdict, _ = deterministic_verdict(evidence)
    assert verdict == "ALERT"


def test_hearing_persists_transcript(tmp_path, mock_client):
    store = LedgerStore(f"sqlite:///{tmp_path / 't.db'}")
    records = load_records("drift_stream.jsonl")[-80:]
    rows = []
    for rec in records:
        ts = datetime.fromisoformat(rec["ts"])
        from drift.sensor.scorer import sense

        features = sense(mock_client, rec)
        row_id = store.append(ts, rec["stream_id"], features)
        rows.append({"id": row_id, "ts": ts, "features": features})

    result = hold_hearing(store, mock_client, "support-bot", rows)
    debate = store.get_debate(result.debate_id)
    assert debate is not None
    assert debate["verdict"] == result.ruling.verdict
    assert debate["prosecutor_argument"]
    assert debate["defense_argument"]
    assert debate["cited_rows"]
    stamped = store.window("support-bot", 5)
    assert all(r["debate_id"] == result.debate_id for r in stamped)
