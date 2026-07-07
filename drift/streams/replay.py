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
        }


def run_replay(
    path: Path,
    store: LedgerStore,
    client: ChatClient | None = None,
    speed: float = 0.0,
    hearing_every: int = HEARING_EVERY,
    window: int = WINDOW_SIZE,
    quiet: bool = False,
) -> ReplaySummary:
    client = client or get_client()
    summary = ReplaySummary()

    cadence = hearing_every
    since_hearing = 0
    open_alert: dict | None = None  # {"debate_id": ..., "ts": ...}
    rolling: list[float] = []
    prev_ts: datetime | None = None

    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            ts = datetime.fromisoformat(record["ts"])
            stream_id = record["stream_id"]
            summary.stream_id = stream_id

            if speed > 0 and prev_ts is not None:
                time.sleep(max(0.0, (ts - prev_ts).total_seconds()) / speed)
            prev_ts = ts

            features = sense(client, record)
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
                result = hold_hearing(store, client, stream_id, rows)
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
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    store = LedgerStore(args.db)
    summary = run_replay(
        args.path, store, speed=args.speed, hearing_every=args.hearing_every, quiet=args.quiet
    )
    print(json.dumps(summary.to_dict(), indent=2))


if __name__ == "__main__":
    main()
