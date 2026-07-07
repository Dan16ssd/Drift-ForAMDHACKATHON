"""Deliver the countdown: one operator sentence + structured payload.

countdown.py computed the numbers; the voice seat (Qwen3-8B live, template in
mock) only phrases the sentence. The payload goes to the webhook (if
configured) and always lands as a COUNTDOWN event for the dashboard.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx

from drift.config import settings
from drift.forecast.countdown import Countdown
from drift.ledger.store import LedgerStore
from drift.llm import EVIDENCE_END, EVIDENCE_START, ChatClient

VOICE_SYSTEM = (
    "You phrase quality-degradation countdowns for operators. Using ONLY the numbers "
    "in the evidence, write one plain sentence: time range until the floor is crossed "
    "and the probable cause. No advice, no filler."
)


def phrase(client: ChatClient, countdown: Countdown) -> str:
    prompt = (
        f"{VOICE_SYSTEM}\n\n{EVIDENCE_START}\n{json.dumps(countdown.to_dict())}\n"
        f"{EVIDENCE_END}\n\nWrite the sentence."
    )
    return client.complete("voice", [{"role": "user", "content": prompt}], temperature=0.0)


def notify(
    store: LedgerStore, client: ChatClient, countdown: Countdown, debate_id: str
) -> dict:
    message = {
        "sentence": phrase(client, countdown),
        "countdown": countdown.to_dict(),
        "debate_id": debate_id,
        "evidence_link": f"/api/debates/{debate_id}",
    }
    webhook = settings().webhook_url
    if webhook:
        try:
            httpx.post(webhook, json={"text": message["sentence"], "drift": message}, timeout=10.0)
        except httpx.HTTPError:
            pass  # notification failure must never stop surveillance
    store.add_event(datetime.now(UTC), countdown.stream_id, "COUNTDOWN", message)
    return message
