#!/usr/bin/env bash
# One-command onboarding onto a fresh OpenAI-compatible endpoint
# (AMD Developer Cloud vLLM/ROCm box, or any serverless API).
#
#   ./scripts/go_live_amd.sh <BASE_URL> <API_KEY>
#
# What it does, in order:
#   1. probes  <BASE_URL>/models and prints the catalog
#   2. verifies every cast seat's model exists in the catalog
#   3. runs the scorer-variance calibration spike (the go/no-go gate)
#   4. replays the planted-drift fixture live with concurrent sensing
#   5. prints how to boot the dashboard / compose stack against the result
#
# Recast seats for the new catalog with env vars before running, e.g.:
#   export DRIFT_MODEL_SCORER=Qwen/Qwen3-30B-A3B      # high-volume seats
#   export DRIFT_MODEL_PROSECUTOR=$DRIFT_MODEL_SCORER
#   export DRIFT_MODEL_DEFENSE=$DRIFT_MODEL_SCORER
#   export DRIFT_MODEL_VOICE=$DRIFT_MODEL_SCORER
#   export DRIFT_MODEL_JUDGE=Qwen/Qwen3-235B-A22B     # the bench
set -euo pipefail

BASE_URL="${1:-${DRIFT_LLM_BASE_URL:-}}"
API_KEY="${2:-${DRIFT_LLM_API_KEY:-}}"
if [[ -z "$BASE_URL" || -z "$API_KEY" ]]; then
    echo "usage: $0 <BASE_URL> <API_KEY>   (or set DRIFT_LLM_BASE_URL / DRIFT_LLM_API_KEY)"
    exit 2
fi
BASE_URL="${BASE_URL%/}"

export DRIFT_LLM_MODE=live
export DRIFT_LLM_BASE_URL="$BASE_URL"
export DRIFT_LLM_API_KEY="$API_KEY"

PY="${PYTHON:-python}"
if [[ -x ".venv/Scripts/python.exe" ]]; then PY=".venv/Scripts/python"; fi
if [[ -x ".venv/bin/python" ]]; then PY=".venv/bin/python"; fi

echo "== 1/4 endpoint catalog ($BASE_URL/models) =="
CATALOG=$(curl -sf -H "Authorization: Bearer $API_KEY" "$BASE_URL/models") || {
    echo "FATAL: could not list models — check the URL and key"; exit 1; }
echo "$CATALOG" | "$PY" -c '
import json, sys
ids = [m["id"] for m in json.load(sys.stdin).get("data", [])]
print("\n".join(f"  {i}" for i in sorted(ids)) or "  (empty catalog)")'

echo
echo "== 2/4 verifying the cast =="
echo "$CATALOG" | "$PY" -c '
import json, sys
from drift.config import MODEL_CASTING
ids = {m["id"] for m in json.load(sys.stdin).get("data", [])}
missing = {s: m for s, m in MODEL_CASTING.items() if m not in ids}
for seat, model in MODEL_CASTING.items():
    mark = "MISSING" if seat in missing else "ok"
    print(f"  {seat:<11} {model}  [{mark}]")
if missing:
    print("\nFATAL: recast the missing seats with DRIFT_MODEL_<SEAT> env vars (see header).")
    sys.exit(1)'

if [[ "${GO_LIVE_STEPS:-all}" == "check" ]]; then
    echo
    echo "GO_LIVE_STEPS=check — stopping after catalog + cast verification."
    exit 0
fi

echo
echo "== 3/4 calibration spike (go/no-go: is scorer noise smaller than drift?) =="
"$PY" -m drift.sensor.calibrate --mode live --repeats 3 --out reports/calibration_amd.json
"$PY" -c '
import json, sys
r = json.load(open("reports/calibration_amd.json"))
sys.exit(0 if r["separable"] else 1)' || {
    echo "NO-GO: scorer repeat noise swamps the drift signal on this endpoint."
    echo "Inspect reports/calibration_amd.json; consider a different scorer model."
    exit 1; }
echo "GO — calibration is separable. Consider lowering DRIFT_QUALITY_FLOOR if the"
echo "     report shows the scorer is stricter than the labels (see README)."

echo
echo "== 4/4 live replay of the planted-drift fixture (concurrent sensing) =="
"$PY" -m drift.streams.replay tests/fixtures/drift_stream.jsonl \
    --db sqlite:///drift_amd.db --concurrency 8

echo
echo "Done. Next:"
echo "  DATABASE_URL=sqlite:///drift_amd.db uvicorn drift.dashboard.server:app --port 8000"
echo "  # or the full stack:  docker compose up -d"
