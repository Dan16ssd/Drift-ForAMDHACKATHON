"""Replay a recorded stream through the full DRIFT pipeline.

record -> sensor (hard metrics + scorer) -> ledger append
       -> sampled hearings (prosecutor / defense / judge)
       -> WATCH tightens sampling; ALERT triggers countdown + notification
       -> outcome backfill when the predicted crossing actually happens

This is both the demo engine and the end-to-end test surface: CI replays the
three fixture streams and asserts the verdicts (drift convicts, stable and
confounder acquit).

Usage:
    python -m drift.streams.replay tests/fixtures/drift_stream.jsonl --speed 0
"""

from __future__ import annotations

import argparse
import json
import time
from collections import deque
from collections.abc import Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from drift.config import (
    HEARING_EVERY,
    HEARING_EVERY_WATCH,
    MIN_SAMPLE,
    QUALITY_FLOOR,
    WINDOW_SIZE,
)
from drift.court.debate import hold_hearing
from drift.forecast.countdown import compute_countdown
from drift.forecast.notify import notify
from drift.ledger.store import LedgerStore
from drift.llm import ChatClient, get_client
from drift.sensor.scorer import sense

ROLLING_N = 15  # rows for the observed-crossing rolling mean


@dataclass
class ReplaySummary:
    stream_id: str = ""
    rows: int = 0
    hearings: list[dict] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)
    countdowns: list[dict] = field(default_factory=list)
    observed_crossing_ts: str | None = None
    outcomes_backfilled: int = 0
    errors: int = 0  # rows/hearings skipped after exhausted retries

    @property
    def verdicts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for h in self.hearings:
            counts[h["verdict"]] = counts.get(h["verdict"], 0) + 1
        return counts

    def alerted(self) -> bool:
        return bool(self.alerts)

    def to_dict(self) -> dict:
        return {
            "stream_id": self.stream_id,
            "rows": self.rows,
            "hearings": len(self.hearings),
            "verdicts": self.verdicts,
            "alerts": self.alerts,
            "countdowns": self.countdowns,
            "observed_crossing_ts": self.observed_crossing_ts,
            "outcomes_backfilled": self.outcomes_backfilled,
            "errors": self.errors,
        }


def _load_ground_truth(path: Path) -> dict | None:
    """A `<stream>.ground_truth.json` sidecar (written by degrade.py) carries
    the planted schedule; when present it is stored as a GROUND_TRUTH event so
    the dashboard can grade the prophecy against reality (demo Act 4)."""
    sidecar = path.with_name(path.stem + ".ground_truth.json")
    if not sidecar.exists():
        return None
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    return {
        "scenario": data.get("scenario"),
        "planted_cause": data.get("planted_cause"),
        "quality_floor": data.get("quality_floor"),
        "first_floor_crossing_ts": data.get("first_floor_crossing_ts"),
        "rows": [
            {"ts": r["ts"], "true_quality": r["true_quality"]} for r in data.get("rows", [])
        ],
    }


def _read_records(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _sensed(
    client: ChatClient, records: Iterable[dict], concurrency: int
) -> Iterator[tuple[dict, dict | Exception]]:
    """Yield (record, features-or-exception) in stream order.

    Sensing one record is independent of every other, so with concurrency > 1
    the LLM scorer calls run ahead in a bounded thread pool — order and
    therefore every downstream verdict stay identical to the sequential run.
    All stateful logic (ledger, hearings, cadence) remains in the consumer.
    """
    if concurrency <= 1:
        for record in records:
            try:
                yield record, sense(client, record)
            except Exception as exc:  # noqa: BLE001
                yield record, exc
        return

    def task(record: dict) -> dict | Exception:
        try:
            return sense(client, record)
        except Exception as exc:  # noqa: BLE001
            return exc

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        pending: deque[tuple[dict, Future[dict | Exception]]] = deque()
        for record in records:
            pending.append((record, pool.submit(task, record)))
            if len(pending) >= concurrency * 2:
                head, fut = pending.popleft()
                yield head, fut.result()
        while pending:
            head, fut = pending.popleft()
            yield head, fut.result()


def run_replay(
    path: Path,
    store: LedgerStore,
    client: ChatClient | None = None,
    speed: float = 0.0,
    hearing_every: int = HEARING_EVERY,
    window: int = WINDOW_SIZE,
    quiet: bool = False,
    concurrency: int = 1,
) -> ReplaySummary:
    client = client or get_client()
    summary = ReplaySummary()
    ground_truth = _load_ground_truth(path)

    cadence = hearing_every
    since_hearing = 0
    open_alert: dict | None = None  # {"debate_id": ..., "ts": ...}
    rolling: list[float] = []
    prev_ts: datetime | None = None

    for record, sensed in _sensed(client, _read_records(path), concurrency):
        ts = datetime.fromisoformat(record["ts"])
        stream_id = record["stream_id"]
        summary.stream_id = stream_id

        if speed > 0 and prev_ts is not None:
            time.sleep(max(0.0, (ts - prev_ts).total_seconds()) / speed)
        prev_ts = ts

        if ground_truth is not None:
            store.add_event(ts, stream_id, "GROUND_TRUTH", ground_truth)
            ground_truth = None  # store once, keyed to the stream's first row

        # Surveillance must survive individual failures: a row that cannot
        # be scored after retries is skipped and counted, never fatal.
        if isinstance(sensed, Exception):
            summary.errors += 1
            if not quiet:
                print(f"[{ts:%H:%M}] sense failed, row skipped: {sensed}")
            continue
        features = sensed
        store.append(ts, stream_id, features)
        summary.rows += 1
        since_hearing += 1

        # Observed ground truth for backfill: rolling mean crosses the floor.
        rolling.append(features["quality"])
        if len(rolling) > ROLLING_N:
            rolling.pop(0)
        rolling_mean = sum(rolling) / len(rolling)
        if (
            summary.observed_crossing_ts is None
            and len(rolling) == ROLLING_N
            and rolling_mean < QUALITY_FLOOR
        ):
            summary.observed_crossing_ts = ts.isoformat()
            if open_alert is not None:
                outcome = {
                    "confirmed": True,
                    "observed_crossing_ts": ts.isoformat(),
                    "detail": f"rolling mean ({ROLLING_N} rows) fell below "
                    f"{QUALITY_FLOOR} after the alert",
                }
                store.backfill_debate_outcome(open_alert["debate_id"], outcome)
                store.add_event(ts, stream_id, "OUTCOME", outcome | open_alert)
                summary.outcomes_backfilled += 1
                open_alert = None

        if summary.rows >= MIN_SAMPLE and since_hearing >= cadence and open_alert is None:
            since_hearing = 0
            rows = store.window(stream_id, window)
            try:
                result = hold_hearing(store, client, stream_id, rows)
            except Exception as exc:  # noqa: BLE001
                summary.errors += 1
                if not quiet:
                    print(f"[{ts:%H:%M}] hearing failed, will re-hear: {exc}")
                continue
            trend = result.evidence.get("trend") or {}
            summary.hearings.append(
                {
                    "ts": ts.isoformat(),
                    "verdict": result.ruling.verdict,
                    "debate_id": result.debate_id,
                    "slope_per_hour": trend.get("slope_per_hour"),
                    "p_value": trend.get("p_value"),
                    "n": trend.get("n"),
                }
            )
            if not quiet:
                print(f"[{ts:%H:%M}] hearing -> {result.ruling.verdict}: "
                      f"{result.ruling.reasoning[:100]}")

            if result.ruling.verdict == "WATCH":
                cadence = HEARING_EVERY_WATCH
            elif result.ruling.verdict == "DISMISS":
                cadence = hearing_every
            elif result.ruling.verdict == "ALERT":
                open_alert = {"debate_id": result.debate_id, "alert_ts": ts.isoformat()}
                summary.alerts.append(dict(open_alert))
                countdown = compute_countdown(rows, stream_id)
                if countdown is not None:
                    message = notify(store, client, countdown, result.debate_id)
                    summary.countdowns.append(message["countdown"] | {
                        "sentence": message["sentence"]
                    })
                    if not quiet:
                        print(f"          countdown: {message['sentence']}")

    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=Path)
    ap.add_argument("--db", default=None, help="database URL (default: DATABASE_URL env)")
    ap.add_argument("--speed", type=float, default=0.0,
                    help="0 = as fast as possible; N = N x real time")
    ap.add_argument("--hearing-every", type=int, default=HEARING_EVERY)
    ap.add_argument("--concurrency", type=int, default=1,
                    help="sensing calls in flight (order-preserving; verdicts identical)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    store = LedgerStore(args.db)
    summary = run_replay(
        args.path, store, speed=args.speed, hearing_every=args.hearing_every,
        quiet=args.quiet, concurrency=args.concurrency,
    )
    print(json.dumps(summary.to_dict(), indent=2))


if __name__ == "__main__":
    main()
