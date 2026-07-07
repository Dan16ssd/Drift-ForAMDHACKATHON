"""The Defense: attacks every prosecution claim with the confounder checklist.

Its mandate is to make ALERT expensive to earn. The checklist results are
deterministic (court.confounders); the seat argues from them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from drift.court.confounders import run_checklist
from drift.court.stats import TrendFit
from drift.llm import EVIDENCE_END, EVIDENCE_START, ChatClient

SYSTEM = (
    "You are the Defense in a quality-degradation hearing. Your mandate: destroy "
    "false alarms. Argue from the confounder checklist results only — traffic mix, "
    "outlier users, time-of-day, scorer noise, sample size. If checks fired, press "
    "them hard; if none fired, concede honestly what was tested and cleared. "
    "3 sentences maximum."
)


@dataclass
class DefenseCase:
    findings: list[dict]
    argument: str


def defend(
    client: ChatClient, rows: list[dict], evidence: dict, aggregate: TrendFit | None
) -> DefenseCase:
    findings = run_checklist(rows, aggregate)
    evidence["confounders"] = findings
    prompt = (
        f"{SYSTEM}\n\n{EVIDENCE_START}\n{json.dumps(evidence)}\n{EVIDENCE_END}\n\n"
        "State your rebuttal."
    )
    argument = client.complete("defense", [{"role": "user", "content": prompt}], temperature=0.0)
    return DefenseCase(findings=findings, argument=argument)
