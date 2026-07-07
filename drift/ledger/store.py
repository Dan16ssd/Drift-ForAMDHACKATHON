"""Ledger access: append, window queries, verdict stamping, outcome backfill."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, desc, func, select, update

from drift.config import settings
from drift.ledger.schema import debates, events, ledger, metadata


def as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; normalize everything to aware UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


class LedgerStore:
    def __init__(self, url: str | None = None) -> None:
        self.engine = create_engine(url or settings().database_url)
        metadata.create_all(self.engine)

    # -- ledger rows -------------------------------------------------------

    def append(self, ts: datetime, stream_id: str, features: dict) -> int:
        with self.engine.begin() as conn:
            res = conn.execute(
                ledger.insert().values(ts=ts, stream_id=stream_id, features=features)
            )
            pk = res.inserted_primary_key
            assert pk is not None
            return int(pk[0])

    def window(self, stream_id: str, limit: int) -> list[dict]:
        """Most recent `limit` rows for a stream, in chronological order."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(ledger)
                .where(ledger.c.stream_id == stream_id)
                .order_by(desc(ledger.c.id))
                .limit(limit)
            ).mappings().all()
        out = [dict(r) for r in reversed(rows)]
        for r in out:
            r["ts"] = as_utc(r["ts"])
        return out

    def stamp_verdict(self, row_ids: list[int], verdict: str, debate_id: str) -> None:
        if not row_ids:
            return
        with self.engine.begin() as conn:
            conn.execute(
                update(ledger)
                .where(ledger.c.id.in_(row_ids))
                .values(verdict=verdict, debate_id=debate_id)
            )

    def backfill_row_outcome(self, row_ids: list[int], outcome: dict) -> None:
        if not row_ids:
            return
        with self.engine.begin() as conn:
            conn.execute(update(ledger).where(ledger.c.id.in_(row_ids)).values(outcome=outcome))

    def streams(self) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(
                    ledger.c.stream_id,
                    func.count(ledger.c.id).label("rows"),
                    func.max(ledger.c.ts).label("last_ts"),
                ).group_by(ledger.c.stream_id)
            ).mappings().all()
        return [
            {
                "stream_id": r["stream_id"],
                "rows": r["rows"],
                "last_ts": as_utc(r["last_ts"]).isoformat(),
            }
            for r in rows
        ]

    # -- debates -----------------------------------------------------------

    def add_debate(self, row: dict) -> None:
        with self.engine.begin() as conn:
            conn.execute(debates.insert().values(**row))

    def get_debate(self, debate_id: str) -> dict | None:
        with self.engine.connect() as conn:
            r = conn.execute(select(debates).where(debates.c.id == debate_id)).mappings().first()
        return dict(r) if r else None

    def list_debates(self, stream_id: str | None = None) -> list[dict]:
        stmt = select(debates).order_by(desc(debates.c.ts))
        if stream_id:
            stmt = stmt.where(debates.c.stream_id == stream_id)
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(r) for r in rows]

    def backfill_debate_outcome(self, debate_id: str, outcome: dict) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(debates).where(debates.c.id == debate_id).values(outcome=outcome))

    # -- events ------------------------------------------------------------

    def add_event(self, ts: datetime, stream_id: str, kind: str, payload: dict) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                events.insert().values(ts=ts, stream_id=stream_id, kind=kind, payload=payload)
            )

    def list_events(
        self, stream_id: str | None = None, kind: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        stmt = select(events).order_by(desc(events.c.id)).limit(limit)
        if stream_id:
            stmt = stmt.where(events.c.stream_id == stream_id)
        if kind:
            stmt = stmt.where(events.c.kind == kind)
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        out = [dict(r) for r in rows]
        for r in out:
            r["ts"] = as_utc(r["ts"]).isoformat()
        return out
