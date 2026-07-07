"""The self-scoring stat: of the ALERTs we raised, how many were real?

Computed from backfilled debate outcomes. Shown live on the dashboard —
the system grading its own judgment in public.
"""

from __future__ import annotations

from drift.ledger.store import LedgerStore


def precision_report(store: LedgerStore, stream_id: str | None = None) -> dict:
    alerts = [d for d in store.list_debates(stream_id) if d["verdict"] == "ALERT"]
    resolved = [d for d in alerts if d.get("outcome")]
    confirmed = [d for d in resolved if d["outcome"].get("confirmed")]
    return {
        "alerts_total": len(alerts),
        "alerts_resolved": len(resolved),
        "alerts_confirmed": len(confirmed),
        "precision": round(len(confirmed) / len(resolved), 3) if resolved else None,
    }
