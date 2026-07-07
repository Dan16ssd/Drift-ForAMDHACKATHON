"""Controlled degradation scenarios — the demo's ground truth machine.

Three seeded generators produce the fixture streams CI asserts verdicts on:

- stable:     healthy noise only                      -> court must NOT alert
- drift:      retrieval relevance decays on schedule  -> court MUST alert
- confounder: per-topic quality constant, traffic mix
              shifts toward hard topics (aggregate
              mean falls, no real degradation)        -> court must NOT alert

The drift scenario writes a ground-truth sidecar (the planted schedule and the
true floor-crossing row) so a forecast can be graded against reality — the
Act-4 overlay in the demo.

Usage:
    python -m drift.streams.degrade --scenario drift --out tests/fixtures/drift_stream.jsonl
    python -m drift.streams.degrade --all --outdir tests/fixtures
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from drift.config import QUALITY_FLOOR
from drift.streams.generate import (
    TOPICS,
    Record,
    SynthesisParams,
    Topic,
    default_start,
    make_record,
)

EASY = [t for t in TOPICS if t.difficulty == "easy"]
HARD = [t for t in TOPICS if t.difficulty == "hard"]


def _clip(x: float) -> float:
    return max(0.02, min(0.98, x))


def _pick_topic(rng: random.Random, p_hard: float) -> Topic:
    pool = HARD if rng.random() < p_hard else EASY
    return rng.choice(pool)


def gen_stable(n: int = 300, seed: int = 11, stream_id: str = "support-bot") -> list[Record]:
    rng = random.Random(seed)
    start = default_start()
    records = []
    for i in range(n):
        topic = _pick_topic(rng, p_hard=0.35)
        q = _clip(rng.gauss(0.85, 0.05))
        params = SynthesisParams(quality=q, retrieval_relevance=0.95)
        records.append(make_record(i, stream_id, topic, params, rng, start))
    return records


def drift_schedule(i: int, n: int, onset_frac: float = 0.33, floor_rel: float = 0.30) -> float:
    """Retrieval relevance over time: healthy until onset, then linear decay."""
    onset = int(n * onset_frac)
    if i < onset:
        return 0.95
    frac = (i - onset) / max(1, n - onset)
    return 0.95 + (floor_rel - 0.95) * frac


def _drift_quality(rel: float, rng: random.Random) -> float:
    return _clip(0.87 * rel + 0.08 + rng.gauss(0, 0.04))


def gen_drift(
    n: int = 300, seed: int = 23, stream_id: str = "support-bot"
) -> tuple[list[Record], dict]:
    rng = random.Random(seed)
    start = default_start()
    records = []
    truth_rows = []
    crossing_idx: int | None = None
    for i in range(n):
        topic = _pick_topic(rng, p_hard=0.35)
        rel = drift_schedule(i, n)
        q = _drift_quality(rel, rng)
        params = SynthesisParams(quality=q, retrieval_relevance=rel)
        rec = make_record(i, stream_id, topic, params, rng, start)
        records.append(rec)
        truth_rows.append(
            {
                "idx": i,
                "ts": rec.ts,
                "retrieval_relevance": round(rel, 6),
                "true_quality": round(q, 6),  # rounded for cross-platform byte-identity
            }
        )
        if crossing_idx is None and q < QUALITY_FLOOR:
            crossing_idx = i
    truth = {
        "scenario": "drift",
        "planted_cause": "retrieval decay",
        "onset_idx": int(n * 0.33),
        "quality_floor": QUALITY_FLOOR,
        "first_floor_crossing_idx": crossing_idx,
        "first_floor_crossing_ts": records[crossing_idx].ts if crossing_idx is not None else None,
        "rows": truth_rows,
    }
    return records, truth


def gen_confounder(n: int = 300, seed: int = 37, stream_id: str = "support-bot") -> list[Record]:
    """Traffic-mix shift ONLY: hard topics grow from 20% to 75% of traffic.

    Per-topic quality is constant over time (easy ~0.88, hard ~0.70, both above
    the floor), so the aggregate mean falls with no degradation anywhere.
    This is the case pure changepoint detection convicts and the Defense must win.
    """
    rng = random.Random(seed)
    start = default_start()
    records = []
    for i in range(n):
        p_hard = 0.20 + 0.55 * (i / max(1, n - 1))
        topic = _pick_topic(rng, p_hard=p_hard)
        base = 0.88 if topic.difficulty == "easy" else 0.70
        q = _clip(rng.gauss(base, 0.04))
        params = SynthesisParams(quality=q, retrieval_relevance=0.95)
        records.append(make_record(i, stream_id, topic, params, rng, start))
    return records


def gen_calibration(n: int = 20, seed: int = 5) -> list[dict]:
    """Labeled set for scorer calibration. Labels here are generation-time
    quality levels rounded to 0.05 — a stand-in until real hand labels replace
    them (documented in README; the calibrate tool is label-source agnostic)."""
    rng = random.Random(seed)
    start = default_start()
    rows = []
    for i in range(n):
        topic = TOPICS[i % len(TOPICS)]
        q = _clip(0.10 + 0.85 * (i / max(1, n - 1)) + rng.gauss(0, 0.02))
        rel = 0.4 + 0.55 * q
        rec = make_record(i, "calibration", topic, SynthesisParams(q, rel), rng, start)
        d = rec.to_dict()
        d["human_label"] = round(round(q / 0.05) * 0.05, 2)
        rows.append(d)
    return rows


def write_jsonl(path: Path, records: list[Record]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" keeps fixtures byte-identical across platforms (CI asserts this)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r.to_dict()) + "\n")


def write_all(outdir: Path, n: int = 300) -> None:
    write_jsonl(outdir / "stable_stream.jsonl", gen_stable(n))
    drift_records, truth = gen_drift(n)
    write_jsonl(outdir / "drift_stream.jsonl", drift_records)
    (outdir / "drift_stream.ground_truth.json").write_text(
        json.dumps(truth, indent=2), encoding="utf-8", newline="\n"
    )
    write_jsonl(outdir / "confounder_stream.jsonl", gen_confounder(n))
    cal = gen_calibration()
    with (outdir / "calibration_set.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for row in cal:
            f.write(json.dumps(row) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", choices=["stable", "drift", "confounder"])
    ap.add_argument("--out", type=Path)
    ap.add_argument("--all", action="store_true", help="write all fixtures to --outdir")
    ap.add_argument("--outdir", type=Path, default=Path("tests/fixtures"))
    ap.add_argument("--n", type=int, default=300)
    args = ap.parse_args()

    if args.all:
        write_all(args.outdir, args.n)
        print(f"wrote all fixtures to {args.outdir}")
        return
    if not args.scenario or not args.out:
        ap.error("--scenario and --out required (or use --all)")
    if args.scenario == "stable":
        write_jsonl(args.out, gen_stable(args.n))
    elif args.scenario == "drift":
        records, truth = gen_drift(args.n)
        write_jsonl(args.out, records)
        args.out.with_suffix("").with_suffix(".ground_truth.json").write_text(
            json.dumps(truth, indent=2), encoding="utf-8", newline="\n"
        )
    else:
        write_jsonl(args.out, gen_confounder(args.n))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
