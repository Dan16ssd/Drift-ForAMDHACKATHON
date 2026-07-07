"""The Prosecutor: argues degradation from deterministic statistical evidence.

Prompted aggressive by design — over-claiming is safe because the Defense
exists. The numbers come from court.stats; the seat only argues them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from drift.config import QUALITY_FLOOR
from drift.court.stats import changepoint_index, fit_trend, project_hours_to_floor
from drift.llm import EVIDENCE_END, EVIDENCE_START, ChatClient

SYSTEM = (
    "You are the Prosecutor in a quality-degradation hearing for a production AI "
    "stream. Argue, from the statistical evidence only, that the stream is degrading "
    "and will cross the quality floor. Be aggressive but cite only numbers present "
    "in the evidence. 3 sentences maximum."
)


@dataclass
class ProsecutionCase:
    evidence: dict
    argument: str


def build_evidence(rows: list[dict]) -> dict:
    fit = fit_trend(rows)
    cp = changepoint_index(rows)
    projected = project_hours_to_floor(fit, QUALITY_FLOOR) if fit else None
    cited = []
    if rows:
        cited = [rows[0]["id"], rows[-1]["id"]]
        if cp is not None:
            cited.insert(1, rows[cp]["id"])
        qmin = min(rows, key=lambda r: r["features"].get("quality", 1.0))
        if qmin["id"] not in cited:
            cited.append(qmin["id"])
    return {
        "trend": fit.to_dict() if fit else None,
        "changepoint_idx": cp,
        "projected_hours_to_floor": round(projected, 2) if projected is not None else None,
        "quality_floor": QUALITY_FLOOR,
        "cited_rows": cited,
    }


def _prompt(evidence: dict) -> str:
    return (
        f"{SYSTEM}\n\n{EVIDENCE_START}\n{json.dumps(evidence)}\n{EVIDENCE_END}\n\n"
        "State your case."
    )


def prosecute(client: ChatClient, rows: list[dict]) -> ProsecutionCase:
    evidence = build_evidence(rows)
    argument = client.complete(
        "prosecutor", [{"role": "user", "content": _prompt(evidence)}], temperature=0.0
    )
    return ProsecutionCase(evidence=evidence, argument=argument)
