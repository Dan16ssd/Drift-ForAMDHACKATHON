"""The Judge: rules DISMISS / WATCH / ALERT with cited reasoning.

The standard of proof is the documented deterministic rule (court.rules). In
mock mode the seat applies it verbatim; in live mode the 235B model rules over
the same evidence with the rule stated as the standard, and any unparseable
ruling falls back to the deterministic rule — a verdict is never lost to a
formatting failure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from drift.court.rules import VERDICTS, deterministic_verdict
from drift.llm import EVIDENCE_END, EVIDENCE_START, ChatClient

SYSTEM = (
    "You are the Judge in a quality-degradation hearing. You have the Prosecutor's "
    "argument, the Defense's rebuttal, and the underlying statistical evidence. "
    "Standard of proof: ALERT requires a significant declining trend (p<0.01, "
    "adequate fit and sample) with every exculpatory confounder cleared; a fired "
    "confounder that explains the decline means DISMISS; suggestive-but-unproven "
    "decline means WATCH (sampling tightens). False ALERTs cause alarm fatigue; "
    "false DISMISSals miss real regressions — both are failures.\n"
    'Reply with ONLY JSON: {"verdict": "DISMISS|WATCH|ALERT", '
    '"reasoning": "<2 sentences citing the evidence>"}'
)


@dataclass
class Ruling:
    verdict: str
    reasoning: str


def rule(
    client: ChatClient, evidence: dict, prosecutor_argument: str, defense_argument: str
) -> Ruling:
    prompt = (
        f"{SYSTEM}\n\n"
        f"### PROSECUTION\n{prosecutor_argument}\n"
        f"### DEFENSE\n{defense_argument}\n\n"
        f"{EVIDENCE_START}\n{json.dumps(evidence)}\n{EVIDENCE_END}\n\n"
        "Rule now."
    )
    raw = client.complete("judge", [{"role": "user", "content": prompt}], temperature=0.0)
    try:
        payload = json.loads(raw)
        verdict = str(payload["verdict"]).upper()
        if verdict not in VERDICTS:
            raise ValueError(verdict)
        return Ruling(verdict=verdict, reasoning=str(payload.get("reasoning", "")))
    except (json.JSONDecodeError, KeyError, ValueError):
        verdict, reasoning = deterministic_verdict(evidence)
        return Ruling(verdict=verdict, reasoning=f"[fallback rule] {reasoning}")
