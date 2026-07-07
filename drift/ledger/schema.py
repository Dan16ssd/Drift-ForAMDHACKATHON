"""Ledger schema — SQLAlchemy Core, one definition for SQLite (dev/CI) and
Postgres (deployment). The append-only drift_ledger is the memory the whole
system reasons over; debates persist every hearing transcript; events feed the
dashboard (WATCH/ALERT/COUNTDOWN/OUTCOME)."""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, MetaData, Table, Text

metadata = MetaData()

PK = BigInteger().with_variant(Integer, "sqlite")

ledger = Table(
    "drift_ledger",
    metadata,
    Column("id", PK, primary_key=True, autoincrement=True),
    Column("ts", DateTime(timezone=True), nullable=False, index=True),
    Column("stream_id", Text, nullable=False, index=True),
    Column("features", JSON, nullable=False),
    Column("verdict", Text),  # DISMISS | WATCH | ALERT | null
    Column("debate_id", Text),
    Column("outcome", JSON),  # backfilled: was the alert real? what did it cost?
)

debates = Table(
    "debates",
    metadata,
    Column("id", Text, primary_key=True),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("stream_id", Text, nullable=False, index=True),
    Column("window_start_id", PK),
    Column("window_end_id", PK),
    Column("evidence", JSON, nullable=False),
    Column("prosecutor_argument", Text),
    Column("defense_argument", Text),
    Column("verdict", Text, nullable=False),
    Column("reasoning", Text),
    Column("cited_rows", JSON),
    Column("outcome", JSON),  # backfilled on ALERT: {"confirmed": bool, ...}
)

events = Table(
    "events",
    metadata,
    Column("id", PK, primary_key=True, autoincrement=True),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("stream_id", Text, nullable=False, index=True),
    Column("kind", Text, nullable=False),  # WATCH | ALERT | COUNTDOWN | OUTCOME
    Column("payload", JSON),
)
