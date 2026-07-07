"""Dashboard API: read-only views over the ledger + built SPA hosting.

Run:  uvicorn drift.dashboard.server:app --port 8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from drift.config import QUALITY_FLOOR, settings
from drift.ledger.precision import precision_report
from drift.ledger.store import LedgerStore

app = FastAPI(title="DRIFT", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

_store: LedgerStore | None = None


def store() -> LedgerStore:
    global _store
    if _store is None:
        _store = LedgerStore()
    return _store


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "llm_mode": settings().llm_mode, "quality_floor": QUALITY_FLOOR}


@app.get("/api/streams")
def streams() -> list[dict]:
    return store().streams()


@app.get("/api/streams/{stream_id}/window")
def window(stream_id: str, limit: int = 300) -> list[dict]:
    rows = store().window(stream_id, limit)
    return [
        {
            "id": r["id"],
            "ts": r["ts"].isoformat(),
            "verdict": r["verdict"],
            "debate_id": r["debate_id"],
            "features": r["features"],
        }
        for r in rows
    ]


@app.get("/api/streams/{stream_id}/debates")
def debates(stream_id: str) -> list[dict]:
    out = store().list_debates(stream_id)
    for d in out:
        d["ts"] = d["ts"].isoformat() if hasattr(d["ts"], "isoformat") else d["ts"]
    return out


@app.get("/api/debates/{debate_id}")
def debate(debate_id: str) -> dict:
    d = store().get_debate(debate_id)
    if d is None:
        raise HTTPException(404, "no such debate")
    d["ts"] = d["ts"].isoformat() if hasattr(d["ts"], "isoformat") else d["ts"]
    return d


@app.get("/api/streams/{stream_id}/events")
def events(stream_id: str, kind: str | None = None, limit: int = 50) -> list[dict]:
    return store().list_events(stream_id=stream_id, kind=kind, limit=limit)


@app.get("/api/streams/{stream_id}/countdown")
def countdown(stream_id: str) -> dict:
    latest = store().list_events(stream_id=stream_id, kind="COUNTDOWN", limit=1)
    return latest[0] if latest else {}


@app.get("/api/precision")
def precision() -> dict:
    return precision_report(store())


_dist = Path(__file__).resolve().parents[2] / "dashboard" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="spa")
