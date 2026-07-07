-- Postgres DDL (deployment asset; dev/CI uses SQLite via SQLAlchemy Core,
-- which generates the equivalent schema from drift/ledger/schema.py).

CREATE TABLE IF NOT EXISTS drift_ledger (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL,
    stream_id   TEXT NOT NULL,
    features    JSONB NOT NULL,
    verdict     TEXT,               -- DISMISS | WATCH | ALERT | null
    debate_id   TEXT,
    outcome     JSONB               -- backfilled: confirmed? cost?
);
CREATE INDEX IF NOT EXISTS ix_ledger_stream_ts ON drift_ledger (stream_id, ts);

CREATE TABLE IF NOT EXISTS debates (
    id                  TEXT PRIMARY KEY,
    ts                  TIMESTAMPTZ NOT NULL,
    stream_id           TEXT NOT NULL,
    window_start_id     BIGINT,
    window_end_id       BIGINT,
    evidence            JSONB NOT NULL,
    prosecutor_argument TEXT,
    defense_argument    TEXT,
    verdict             TEXT NOT NULL,
    reasoning           TEXT,
    cited_rows          JSONB,
    outcome             JSONB
);
CREATE INDEX IF NOT EXISTS ix_debates_stream ON debates (stream_id, ts);

CREATE TABLE IF NOT EXISTS events (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL,
    stream_id   TEXT NOT NULL,
    kind        TEXT NOT NULL,      -- WATCH | ALERT | COUNTDOWN | OUTCOME
    payload     JSONB
);
CREATE INDEX IF NOT EXISTS ix_events_stream ON events (stream_id, id);
