"""Scorer calibration + variance spike (spec risk #2, the Day-1 go/no-go).

Scores a labeled set N times and reports:
- per-item variance across repeats (scorer stability; ~0 in mock mode, the
  number that matters once a real endpoint is wired)
- agreement with labels (MAE, Pearson r)
- separability: gap between top- and bottom-tercile means vs pooled repeat std.
  If the gap does not dominate the noise, drift of that magnitude is invisible
  to this scorer — that is the no-go signal.

Usage:
    python -m drift.sensor.calibrate --set tests/fixtures/calibration_set.jsonl --repeats 3
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from drift.llm import get_client
from drift.sensor.scorer import score_quality


def run_calibration(set_path: Path, repeats: int = 3, mode: str | None = None) -> dict:
    rows = [json.loads(line) for line in set_path.read_text(encoding="utf-8").splitlines() if line]
    client = get_client(mode)

    items = []
    for row in rows:
        scores = [score_quality(client, row) for _ in range(repeats)]
        items.append(
            {
                "idx": row.get("idx"),
                "topic": row.get("topic"),
                "human_label": row.get("human_label"),
                "scores": scores,
                "mean": statistics.mean(scores),
                "std": statistics.pstdev(scores) if len(scores) > 1 else 0.0,
            }
        )

    labels = [i["human_label"] for i in items]
    means = [i["mean"] for i in items]
    mae = statistics.mean(abs(a - b) for a, b in zip(labels, means, strict=True))
    r = _pearson(labels, means)
    pooled_std = statistics.mean(i["std"] for i in items)

    ranked = sorted(items, key=lambda i: i["human_label"])
    k = max(1, len(ranked) // 3)
    bottom = statistics.mean(i["mean"] for i in ranked[:k])
    top = statistics.mean(i["mean"] for i in ranked[-k:])
    gap = top - bottom
    separable = gap > 4 * pooled_std if pooled_std > 0 else gap > 0.15

    return {
        "n_items": len(items),
        "repeats": repeats,
        "mae_vs_label": round(mae, 4),
        "pearson_r": round(r, 4),
        "mean_repeat_std": round(pooled_std, 4),
        "tercile_gap": round(gap, 4),
        "separable": separable,
        "items": items,
    }


def _pearson(xs: list[float], ys: list[float]) -> float:
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", type=Path, default=Path("tests/fixtures/calibration_set.jsonl"))
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--mode", choices=["mock", "live"], default=None)
    ap.add_argument("--out", type=Path, default=Path("reports/calibration.json"))
    args = ap.parse_args()

    report = run_calibration(args.set, args.repeats, args.mode)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"items={report['n_items']} repeats={report['repeats']}")
    print(f"MAE vs label     : {report['mae_vs_label']}")
    print(f"Pearson r        : {report['pearson_r']}")
    print(f"mean repeat std  : {report['mean_repeat_std']}")
    print(f"tercile gap      : {report['tercile_gap']}")
    print(f"SEPARABLE (go)   : {report['separable']}")
    print(f"report -> {args.out}")


if __name__ == "__main__":
    main()
