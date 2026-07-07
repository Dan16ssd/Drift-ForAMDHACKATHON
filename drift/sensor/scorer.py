"""LLM-as-judge quality scorer with a frozen rubric, temperature 0.

The same prompt is built in mock and live mode; the mock seat parses it and
answers with a deterministic heuristic (see drift.sensor.heuristic), the live
seat is Qwen3-30B-A3B on the serving endpoint.
"""

from __future__ import annotations

import json
import re

from drift.llm import ChatClient
from drift.sensor.metrics import hard_metrics

RUBRIC = """You are a strict quality scorer for a customer-support AI. Score the RESPONSE
against the REFERENCE answer for the QUESTION on a 0.0-1.0 scale:

1.0  fully correct, complete, direct, grounded in the reference
0.8  correct with minor omissions
0.6  mostly correct but incomplete, hedged, or padded  <- the acceptability floor
0.4  significant omissions or off-topic content mixed in
0.2  mostly wrong, evasive, truncated, or heavily hedged
0.0  refusal, empty, or entirely wrong

Penalize: content not supported by the reference, hedging, truncation,
refusing answerable questions. Do not reward verbosity.

Reply with ONLY a JSON object: {"score": <float>, "rationale": "<one sentence>"}"""

_FLOAT_RE = re.compile(r"\b(0?\.\d+|1\.0|0|1)\b")


def build_prompt(record: dict) -> str:
    return (
        f"{RUBRIC}\n\n"
        f"### QUESTION\n{record.get('question', '')}\n"
        f"### REFERENCE\n{record.get('reference', '')}\n"
        f"### RESPONSE\n{record.get('response', '')}\n"
        f"### END\n"
    )


def parse_score(raw: str) -> float:
    try:
        payload = json.loads(raw)
        return max(0.0, min(1.0, float(payload["score"])))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        m = _FLOAT_RE.search(raw)
        if m:
            return max(0.0, min(1.0, float(m.group(1))))
        return 0.0


def score_quality(client: ChatClient, record: dict) -> float:
    raw = client.complete(
        "scorer",
        [{"role": "user", "content": build_prompt(record)}],
        temperature=0.0,
    )
    return parse_score(raw)


def sense(client: ChatClient, record: dict) -> dict:
    """Full sensor pass: hard metrics + LLM quality score -> feature vector."""
    features = hard_metrics(record)
    features["quality"] = round(score_quality(client, record), 4)
    # Context the court's confounder checks need, carried with the features.
    features["topic"] = record.get("topic", "")
    features["difficulty"] = record.get("difficulty", "")
    features["user_id"] = record.get("user_id", "")
    # Text excerpts so the dashboard can show the actual exchange next to the
    # scores (demo Acts 1 and 4: "responses visibly good" / good-vs-bad).
    features["question"] = record.get("question", "")
    features["response_excerpt"] = (record.get("response", "") or "")[:600]
    return features
