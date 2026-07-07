"""Heuristic quality score used by the mock scorer seat.

A real function of the response text — reference recall, precision against
off-topic content, hedging, truncation, refusals — NOT a lookup of the
generator's planted quality. This keeps mock-mode drift detection honest:
degradation must be visible in the text to be scored down.
"""

from __future__ import annotations

from drift.sensor.metrics import hedge_count, is_refusal, is_truncated, tokens


def heuristic_score(question: str, reference: str, response: str) -> float:
    if not response.strip():
        return 0.0
    if is_refusal(response):
        return 0.05

    ref = tokens(reference)
    resp = tokens(response)
    ref_set, resp_set = set(ref), set(resp)
    recall = sum(1 for w in ref if w in resp_set) / len(ref) if ref else 0.0
    precision = sum(1 for w in resp if w in ref_set) / len(resp) if resp else 0.0

    hedge_norm = min(1.0, hedge_count(response) / 4.0)

    score = (
        1.05 * recall
        + 0.15 * (1.0 - hedge_norm)
        - 0.10 * (1.0 - precision)
        - 0.15 * (1.0 if is_truncated(response) else 0.0)
    )
    return max(0.0, min(1.0, score))
