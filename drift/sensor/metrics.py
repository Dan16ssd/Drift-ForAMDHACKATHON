"""Hard metrics — pure functions over a response record. No LLM anywhere."""

from __future__ import annotations

import re

STOPWORDS = frozenset(
    """a an and are as at be but by for from has have i if in is it its of on or
    that the to was we what when where which who why will with you your our this
    do does how can my me""".split()
)

HEDGE_MARKERS = [
    "i think",
    "perhaps",
    "might be",
    "i'm not entirely sure",
    "not sure",
    "possibly",
    "it depends",
    "as far as i know",
    "i believe",
    "maybe",
]

REFUSAL_MARKERS = [
    "unable to help",
    "can't assist",
    "cannot assist",
    "can't help with that",
    "cannot help with that",
]

_WORD_RE = re.compile(r"[a-z0-9']+")


def tokens(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if w not in STOPWORDS]


def length_words(text: str) -> int:
    return len(_WORD_RE.findall(text.lower()))


def is_refusal(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in REFUSAL_MARKERS)


def hedge_count(text: str) -> int:
    low = text.lower()
    return sum(low.count(m) for m in HEDGE_MARKERS)


def hedge_rate(text: str) -> float:
    """Hedge markers per 100 words."""
    n = length_words(text)
    return 100.0 * hedge_count(text) / n if n else 0.0


def is_truncated(text: str) -> bool:
    stripped = text.rstrip().rstrip('"').rstrip("'")
    return bool(stripped) and stripped[-1] not in ".!?"


def _overlap(a: list[str], b: set[str]) -> float:
    return sum(1 for w in a if w in b) / len(a) if a else 0.0


def retrieval_hit_ratio(snippets: list[dict], reference: str) -> float:
    """Fraction of retrieved snippets that are relevant to the canonical answer.

    In this demo relevance is measured against the reference doc; in a live
    deployment the same measure runs against the query/domain corpus.
    """
    if not snippets:
        return 0.0
    ref = set(tokens(reference))
    hits = sum(1 for s in snippets if _overlap(tokens(s.get("text", "")), ref) >= 0.5)
    return hits / len(snippets)


def adherence(question: str, response: str) -> float:
    """Fraction of the question's content words addressed in the response."""
    q = tokens(question)
    if not q:
        return 1.0
    resp = set(tokens(response))
    return sum(1 for w in q if w in resp) / len(q)


def hard_metrics(record: dict) -> dict:
    """Compute all deterministic features for one response record."""
    response = record.get("response", "")
    return {
        "latency_ms": float(record.get("latency_ms", 0.0)),
        "length_words": length_words(response),
        "refusal": 1.0 if is_refusal(response) else 0.0,
        "hedge_rate": round(hedge_rate(response), 3),
        "truncated": 1.0 if is_truncated(response) else 0.0,
        "retrieval_hit_ratio": round(
            retrieval_hit_ratio(record.get("snippets", []), record.get("reference", "")), 3
        ),
        "adherence": round(adherence(record.get("question", ""), response), 3),
    }
