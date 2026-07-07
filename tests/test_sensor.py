from __future__ import annotations

from drift.sensor.calibrate import run_calibration
from drift.sensor.heuristic import heuristic_score
from drift.sensor.metrics import (
    adherence,
    hedge_rate,
    is_refusal,
    is_truncated,
    retrieval_hit_ratio,
)
from drift.sensor.scorer import parse_score, sense
from tests.conftest import FIXTURES, load_records

REF = (
    "To reset your password, open the sign-in page and click the Forgot password link. "
    "Enter the email address associated with your account and submit the form. "
    "We send a reset link that stays valid for 30 minutes."
)


def test_refusal_detection():
    assert is_refusal("I'm sorry, but I'm unable to help with that request.")
    assert not is_refusal("Open the sign-in page and click Forgot password.")


def test_truncation_detection():
    assert is_truncated("Enter the email address associated with your acc")
    assert not is_truncated("Enter the email address. Then submit the form.")


def test_hedge_rate_orders_hedged_text():
    confident = "Open the sign-in page and click the link."
    hedged = "I think, perhaps, it might be the case that you open the page, I believe."
    assert hedge_rate(hedged) > hedge_rate(confident)


def test_retrieval_hit_ratio():
    good = [{"text": "To reset your password, open the sign-in page and click the link."}]
    bad = [{"text": "Webhooks are delivered as POST requests with an X-Signature header."}]
    assert retrieval_hit_ratio(good, REF) == 1.0
    assert retrieval_hit_ratio(bad, REF) == 0.0
    assert retrieval_hit_ratio(good + bad, REF) == 0.5


def test_adherence():
    q = "How do I reset my password?"
    assert adherence(q, "To reset your password, click the link.") > adherence(q, "Contact sales.")


def test_heuristic_score_orders_quality():
    q = "How do I reset my password?"
    good = REF
    mediocre = (
        "I think, to reset your password, open the sign-in page and click the link. "
        "Refunds are available within 30 days of any charge on your account."
    )
    bad = "Perhaps, I believe, refunds are available within 30 days"
    s_good = heuristic_score(q, REF, good)
    s_med = heuristic_score(q, REF, mediocre)
    s_bad = heuristic_score(q, REF, bad)
    assert s_good > s_med > s_bad
    assert heuristic_score(q, REF, "I'm sorry, but I'm unable to help with that request.") <= 0.1


def test_parse_score_fallback():
    assert parse_score('{"score": 0.73, "rationale": "x"}') == 0.73
    assert parse_score("the score is 0.4 overall") == 0.4
    assert parse_score("garbage") == 0.0


def test_sense_produces_full_feature_vector(mock_client):
    rec = load_records("stable_stream.jsonl")[0]
    features = sense(mock_client, rec)
    for key in (
        "quality", "latency_ms", "length_words", "refusal", "hedge_rate",
        "truncated", "retrieval_hit_ratio", "adherence", "topic", "difficulty", "user_id",
    ):
        assert key in features
    assert 0.0 <= features["quality"] <= 1.0


def test_calibration_separability():
    """The mock-mode variance spike: scorer must separate quality terciles."""
    report = run_calibration(FIXTURES / "calibration_set.jsonl", repeats=2, mode="mock")
    assert report["separable"], report
    assert report["pearson_r"] > 0.7, report
    assert report["mean_repeat_std"] == 0.0  # mock is deterministic at temp 0
