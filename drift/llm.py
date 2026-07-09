"""OpenAI-compatible chat client with a deterministic mock backend.

Every LLM seat (scorer, prosecutor, defense, judge, voice) goes through
`ChatClient.complete(seat, messages)`. Live mode posts to any OpenAI-compatible
/chat/completions endpoint (Fireworks, vLLM on AMD Developer Cloud). Mock mode
answers deterministically by parsing the *same prompts* the live models see:

- scorer   -> extracts QUESTION/REFERENCE/RESPONSE sections and computes a
              real heuristic over the text (not a ground-truth lookup)
- pros/def -> extracts the EVIDENCE JSON block and templates an argument
- judge    -> extracts the EVIDENCE JSON block and applies the documented
              deterministic decision rule from drift.court.rules
- voice    -> extracts the COUNTDOWN JSON block and phrases one sentence

This keeps a single code path: prompts are built identically in both modes,
and CI exercises the full pipeline with zero API keys.
"""

from __future__ import annotations

import json
import re
import time
from typing import Protocol

import httpx

from drift.config import MODEL_CASTING, NO_THINK_SEATS, seat_endpoint, settings

# Markers shared by prompt builders and the mock parser.
SECTION_RE = re.compile(r"^### (\w+)\s*$", re.MULTILINE)
EVIDENCE_START = "### EVIDENCE_JSON"
EVIDENCE_END = "### END_EVIDENCE"


class ChatClient(Protocol):
    def complete(
        self, seat: str, messages: list[dict[str, str]], temperature: float = 0.0
    ) -> str: ...


_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def strip_think(content: str) -> str:
    """Qwen3 models emit <think>...</think> reasoning blocks; the seats' output
    contracts (JSON verdicts, scores, one sentence) apply to what follows."""
    return _THINK_RE.sub("", content).strip()


def parse_sections(prompt: str) -> dict[str, str]:
    """Split a prompt into its '### NAME' sections (used by mock responders)."""
    parts = SECTION_RE.split(prompt)
    # parts = [preamble, name1, body1, name2, body2, ...]
    sections: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        sections[parts[i]] = parts[i + 1].strip()
    return sections


def extract_json_block(prompt: str) -> dict:
    """Extract the JSON payload between EVIDENCE markers."""
    start = prompt.index(EVIDENCE_START) + len(EVIDENCE_START)
    end = prompt.index(EVIDENCE_END)
    return json.loads(prompt[start:end].strip())


class LiveChatClient:
    """Any OpenAI-compatible endpoint; model AND endpoint chosen per seat.

    MODEL_CASTING picks the model; DRIFT_BASE_URL_<SEAT>/DRIFT_API_KEY_<SEAT>
    can move a seat to another host (fallback: the global base_url/api_key),
    so e.g. the per-response scorer runs on a flat-cost vLLM/ROCm box while
    the judge stays on a serverless API. httpx.Client is thread-safe, so one
    instance serves the replay's concurrent sensing pool.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        cfg = settings()
        self.base_url = (base_url or cfg.llm_base_url).rstrip("/")
        self.api_key = api_key or cfg.llm_api_key
        self._http = httpx.Client(timeout=120.0)

    RETRIES = 4  # attempts on timeouts / transport errors / 429 / 5xx

    def complete(
        self, seat: str, messages: list[dict[str, str]], temperature: float = 0.0
    ) -> str:
        model = MODEL_CASTING[seat]
        # Hybrid Qwen3 checkpoints think by default; the split -instruct-2507 /
        # -thinking-2507 variants ignore the switch, so it is safe to send.
        if seat in NO_THINK_SEATS and "qwen3" in model and "thinking" not in model:
            messages = [*messages[:-1], {**messages[-1],
                        "content": messages[-1]["content"] + "\n/no_think"}]
        base_url, api_key = seat_endpoint(seat, self.base_url, self.api_key)
        payload = {"model": model, "messages": messages, "temperature": temperature}
        last_exc: Exception | None = None
        for attempt in range(self.RETRIES):
            try:
                resp = self._http.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    resp.raise_for_status()
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                return strip_think(content)
            except httpx.HTTPStatusError as e:
                # Client errors other than 429 are permanent; don't retry.
                if e.response.status_code != 429 and e.response.status_code < 500:
                    raise
                last_exc = e
            except httpx.HTTPError as e:  # timeouts, transport failures
                last_exc = e
            time.sleep(2**attempt)  # 1s, 2s, 4s
        assert last_exc is not None
        raise last_exc


class MockChatClient:
    """Deterministic stand-in that parses the real prompts. No network, no keys."""

    def complete(
        self, seat: str, messages: list[dict[str, str]], temperature: float = 0.0
    ) -> str:
        prompt = messages[-1]["content"]
        if seat == "scorer":
            return self._score(prompt)
        if seat in ("prosecutor", "defense"):
            return self._argue(seat, prompt)
        if seat == "judge":
            return self._rule(prompt)
        if seat == "voice":
            return self._phrase(prompt)
        raise ValueError(f"unknown seat: {seat}")

    def _score(self, prompt: str) -> str:
        from drift.sensor.heuristic import heuristic_score

        s = parse_sections(prompt)
        score = heuristic_score(
            question=s.get("QUESTION", ""),
            reference=s.get("REFERENCE", ""),
            response=s.get("RESPONSE", ""),
        )
        return json.dumps({"score": round(score, 4), "rationale": "heuristic (mock mode)"})

    def _argue(self, seat: str, prompt: str) -> str:
        ev = extract_json_block(prompt)
        if seat == "prosecutor":
            t = ev.get("trend", {})
            return (
                f"The quality trend over the last {t.get('n', '?')} responses is "
                f"declining at {t.get('slope_per_hour', 0):+.4f}/hour "
                f"(R²={t.get('r2', 0):.2f}, p={t.get('p_value', 1):.4g}). "
                f"At this rate the stream crosses the quality floor in "
                f"{ev.get('projected_hours_to_floor', 'N/A')} hours. "
                "This is degradation, not noise."
            )
        fired = [f["name"] for f in ev.get("confounders", []) if f["fired"]]
        if fired:
            return (
                "The prosecution's trend does not survive scrutiny: "
                + "; ".join(fired)
                + ". The apparent decline is explained without any model degradation."
            )
        return (
            "No confounder in the checklist (traffic mix, outlier users, time-of-day, "
            "scorer noise, sample size) explains the decline. The defense rests on the "
            "residual possibility of unmodeled variance."
        )

    def _rule(self, prompt: str) -> str:
        from drift.court.rules import deterministic_verdict

        ev = extract_json_block(prompt)
        verdict, reasoning = deterministic_verdict(ev)
        return json.dumps({"verdict": verdict, "reasoning": reasoning})

    def _phrase(self, prompt: str) -> str:
        ev = extract_json_block(prompt)
        lo, hi = ev.get("hours_low"), ev.get("hours_high")
        cause = ev.get("probable_cause", "unknown cause")
        return (
            f"Quality crosses your floor in ~{lo}–{hi} hours at the current rate; "
            f"probable cause: {cause}."
        )


def get_client(mode: str | None = None) -> ChatClient:
    mode = (mode or settings().llm_mode).lower()
    if mode == "live":
        return LiveChatClient()
    return MockChatClient()
