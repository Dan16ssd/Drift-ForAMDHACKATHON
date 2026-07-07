"""One hearing: evidence -> prosecution -> defense -> ruling, fully persisted.

Every hearing leaves a transcript row in the debates table and stamps the
verdict + debate id onto the ledger rows it examined. An alert is never a
threshold crossing; it is a verdict with a browsable transcript.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from drift.court.defense import defend
from drift.court.judge import Ruling, rule
from drift.court.prosecutor import prosecute
from drift.court.stats import fit_trend
from drift.ledger.store import LedgerStore
from drift.llm import ChatClient


@dataclass
class HearingResult:
    debate_id: str
    ruling: Ruling
    evidence: dict


def hold_hearing(
    store: LedgerStore, client: ChatClient, stream_id: str, rows: list[dict]
) -> HearingResult:
    debate_id = str(uuid.uuid4())
    aggregate = fit_trend(rows)

    case = prosecute(client, rows)
    rebuttal = defend(client, rows, case.evidence, aggregate)  # adds confounders to evidence
    ruling = rule(client, case.evidence, case.argument, rebuttal.argument)

    now = rows[-1]["ts"] if rows else datetime.now(UTC)
    store.add_debate(
        {
            "id": debate_id,
            "ts": now,
            "stream_id": stream_id,
            "window_start_id": rows[0]["id"] if rows else None,
            "window_end_id": rows[-1]["id"] if rows else None,
            "evidence": case.evidence,
            "prosecutor_argument": case.argument,
            "defense_argument": rebuttal.argument,
            "verdict": ruling.verdict,
            "reasoning": ruling.reasoning,
            "cited_rows": case.evidence.get("cited_rows", []),
        }
    )
    store.stamp_verdict([r["id"] for r in rows], ruling.verdict, debate_id)
    if ruling.verdict in ("WATCH", "ALERT"):
        store.add_event(
            now,
            stream_id,
            ruling.verdict,
            {"debate_id": debate_id, "reasoning": ruling.reasoning},
        )
    return HearingResult(debate_id=debate_id, ruling=ruling, evidence=case.evidence)
