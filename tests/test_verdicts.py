"""THE three fixture verdicts — a green run here is a machine-checked claim
that the court convicts real drift, acquits noise, and acquits a traffic-mix
shift that superficially looks like decay (the hard case).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from drift.ledger.precision import precision_report
from drift.ledger.store import LedgerStore
from drift.streams.replay import run_replay
from tests.conftest import FIXTURES


def replay(name: str, tmp_path, mock_client):
    store = LedgerStore(f"sqlite:///{tmp_path / (name + '.db')}")
    summary = run_replay(FIXTURES / name, store, client=mock_client, quiet=True)
    return store, summary


def test_drift_stream_convicts_and_grades_itself(tmp_path, mock_client):
    store, summary = replay("drift_stream.jsonl", tmp_path, mock_client)

    assert summary.alerted(), summary.to_dict()
    assert summary.countdowns, "ALERT must come with a countdown"

    # The prophecy is graded: the observed crossing happened, the alert outcome
    # was backfilled, and precision is computable.
    assert summary.observed_crossing_ts is not None
    assert summary.outcomes_backfilled >= 1
    report = precision_report(store)
    assert report["alerts_confirmed"] >= 1
    assert report["precision"] == 1.0

    # The first countdown's window brackets the observed crossing (±2h grace).
    cd = summary.countdowns[0]
    as_of = datetime.fromisoformat(cd["as_of"])
    observed = datetime.fromisoformat(summary.observed_crossing_ts)
    low = as_of + timedelta(hours=cd["hours_low"]) - timedelta(hours=2)
    high_h = cd["hours_high"] if cd["hours_high"] is not None else cd["hours_best"] * 3
    high = as_of + timedelta(hours=high_h) + timedelta(hours=2)
    assert low <= observed <= high, (cd, summary.observed_crossing_ts)

    # Cause attribution names the planted cause.
    assert cd["probable_cause"] == "retrieval decay"


def test_stable_stream_acquits(tmp_path, mock_client):
    _, summary = replay("stable_stream.jsonl", tmp_path, mock_client)
    assert len(summary.hearings) >= 3, "surveillance must actually run"
    assert not summary.alerted(), summary.to_dict()
    assert summary.observed_crossing_ts is None


def test_confounder_stream_acquits_the_hard_case(tmp_path, mock_client):
    _, summary = replay("confounder_stream.jsonl", tmp_path, mock_client)
    assert len(summary.hearings) >= 3, "surveillance must actually run"
    assert not summary.alerted(), summary.to_dict()
