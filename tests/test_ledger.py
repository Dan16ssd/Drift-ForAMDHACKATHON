from __future__ import annotations

from datetime import UTC, datetime, timedelta

from drift.ledger.precision import precision_report
from drift.ledger.store import LedgerStore


def make_store(tmp_path) -> LedgerStore:
    return LedgerStore(f"sqlite:///{tmp_path / 'test.db'}")


def test_append_and_window_order(tmp_path):
    store = make_store(tmp_path)
    t0 = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    ids = [
        store.append(t0 + timedelta(minutes=i), "s1", {"quality": 0.8, "idx": i})
        for i in range(5)
    ]
    rows = store.window("s1", 3)
    assert [r["id"] for r in rows] == ids[-3:]  # chronological, most recent 3
    assert rows[0]["ts"].tzinfo is not None


def test_verdict_stamping_and_debates(tmp_path):
    store = make_store(tmp_path)
    t0 = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    ids = [store.append(t0, "s1", {"quality": 0.5}) for _ in range(3)]
    store.add_debate(
        {
            "id": "d1", "ts": t0, "stream_id": "s1",
            "window_start_id": ids[0], "window_end_id": ids[-1],
            "evidence": {"trend": None}, "prosecutor_argument": "p",
            "defense_argument": "d", "verdict": "ALERT", "reasoning": "r",
            "cited_rows": ids,
        }
    )
    store.stamp_verdict(ids, "ALERT", "d1")
    rows = store.window("s1", 10)
    assert all(r["verdict"] == "ALERT" and r["debate_id"] == "d1" for r in rows)
    assert store.get_debate("d1")["verdict"] == "ALERT"


def test_precision_report(tmp_path):
    store = make_store(tmp_path)
    t0 = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    base = {
        "ts": t0, "stream_id": "s1", "window_start_id": 1, "window_end_id": 2,
        "evidence": {}, "prosecutor_argument": "", "defense_argument": "",
        "reasoning": "", "cited_rows": [],
    }
    store.add_debate(base | {"id": "a1", "verdict": "ALERT"})
    store.add_debate(base | {"id": "a2", "verdict": "ALERT"})
    store.add_debate(base | {"id": "w1", "verdict": "WATCH"})
    store.backfill_debate_outcome("a1", {"confirmed": True})
    report = precision_report(store)
    assert report["alerts_total"] == 2
    assert report["alerts_resolved"] == 1
    assert report["precision"] == 1.0


def test_events(tmp_path):
    store = make_store(tmp_path)
    t0 = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    store.add_event(t0, "s1", "COUNTDOWN", {"hours_best": 4.0})
    events = store.list_events(stream_id="s1", kind="COUNTDOWN")
    assert len(events) == 1
    assert events[0]["payload"]["hours_best"] == 4.0
