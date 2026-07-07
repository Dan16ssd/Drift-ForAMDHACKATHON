"""Synthetic support-bot corpus and response synthesis.

The bank models a SaaS support bot: each topic has user question variants, a
reference answer (sentences drawn from the product docs), and doc snippets the
"retrieval" step returns. Degradation is planted *in the text itself* —
truncation, hedging, wrong-topic (decoy) retrieval content — so any honest
scorer, heuristic or LLM, has to detect it from the response alone. Ground
truth is never written into the records the pipeline sees.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

HEDGES = [
    "I think", "perhaps", "it might be the case that", "I'm not entirely sure, but",
    "possibly", "it depends, but", "as far as I know", "I believe",
]

REFUSALS = [
    "I'm sorry, but I'm unable to help with that request.",
    "I can't assist with this. Please contact support directly.",
]


@dataclass(frozen=True)
class Topic:
    name: str
    difficulty: str  # "easy" | "hard"
    questions: list[str]
    doc: list[str]  # reference answer sentences == retrievable snippets


TOPICS: list[Topic] = [
    Topic(
        name="password-reset",
        difficulty="easy",
        questions=[
            "How do I reset my password?",
            "I forgot my password, what should I do?",
            "Where is the password reset option?",
        ],
        doc=[
            "To reset your password, open the sign-in page and click the Forgot password link.",
            "Enter the email address associated with your account and submit the form.",
            "We send a reset link that stays valid for 30 minutes.",
            "Click the link, choose a new password of at least 12 characters, and confirm it.",
            "If the email does not arrive, check your spam folder or request a new link.",
        ],
    ),
    Topic(
        name="billing-refund",
        difficulty="easy",
        questions=[
            "How do I request a refund?",
            "Can I get my money back for last month's charge?",
            "What is your refund policy?",
        ],
        doc=[
            "Refunds are available within 30 days of any charge on your account.",
            "Open Billing in your workspace settings and select the invoice you want refunded.",
            "Click Request refund and choose a reason from the dropdown.",
            "Approved refunds are returned to the original payment method within 5 business days.",
            "Annual plans are refunded pro rata for the unused months.",
        ],
    ),
    Topic(
        name="shipping-status",
        difficulty="easy",
        questions=[
            "Where is my order?",
            "How can I track my shipment?",
            "My package has not arrived yet, what can I do?",
        ],
        doc=[
            "You can track any order from the Orders page in your account.",
            "Click the order number to see the carrier, tracking code, and current status.",
            "Standard shipping takes 3 to 7 business days after dispatch.",
            "If a package is marked delivered but missing, wait 24 hours and check with neighbours.",
            "For orders delayed more than 10 days, open a support ticket for a replacement.",
        ],
    ),
    Topic(
        name="account-deletion",
        difficulty="easy",
        questions=[
            "How do I delete my account?",
            "I want to permanently remove my account and data.",
            "Can I close my account?",
        ],
        doc=[
            "You can delete your account from Settings under the Privacy tab.",
            "Click Delete account and type your email address to confirm.",
            "Deletion is permanent and removes all projects, files, and personal data.",
            "We keep invoices for 7 years where tax law requires it.",
            "The deletion completes within 30 days and you receive a confirmation email.",
        ],
    ),
    Topic(
        name="api-webhooks",
        difficulty="hard",
        questions=[
            "Why are my webhooks not firing?",
            "How do I verify webhook signatures?",
            "My webhook endpoint keeps getting disabled, why?",
        ],
        doc=[
            "Webhooks are delivered as POST requests with a JSON body and an X-Signature header.",
            "Verify the signature by computing an HMAC-SHA256 of the raw body with your signing secret.",
            "Endpoints must respond with a 2xx status within 10 seconds or the delivery is retried.",
            "We retry failed deliveries 5 times with exponential backoff over 24 hours.",
            "An endpoint that fails for 3 consecutive days is disabled automatically and must be re-enabled in the dashboard.",
        ],
    ),
    Topic(
        name="sso-saml",
        difficulty="hard",
        questions=[
            "How do I set up SAML single sign-on?",
            "Our SSO login loops back to the sign-in page, how do we fix it?",
            "Which identity providers do you support for SSO?",
        ],
        doc=[
            "SAML SSO is available on the Enterprise plan and is configured under Security settings.",
            "Upload your identity provider metadata XML or enter the SSO URL and certificate manually.",
            "Set the audience URI and ACS URL exactly as shown in the setup panel.",
            "A login loop usually means the clock on the identity provider is skewed or the certificate rotated.",
            "We support Okta, Azure AD, Google Workspace, and any SAML 2.0 compliant provider.",
        ],
    ),
    Topic(
        name="data-export",
        difficulty="hard",
        questions=[
            "How can I export all my data for GDPR compliance?",
            "I need a full export of my workspace, how does that work?",
            "What format do data exports come in?",
        ],
        doc=[
            "Workspace admins can request a full export from Settings under Data management.",
            "Exports include all projects, comments, attachments, and audit logs.",
            "The export is packaged as a ZIP of JSON files with attachments in their original format.",
            "Large workspaces are processed in the background and you are emailed a download link.",
            "Download links are valid for 72 hours and can be regenerated at any time.",
        ],
    ),
    Topic(
        name="rate-limits",
        difficulty="hard",
        questions=[
            "What are the API rate limits?",
            "I keep hitting 429 errors, how do I avoid them?",
            "Can I get a higher rate limit for my integration?",
        ],
        doc=[
            "The API allows 600 requests per minute per token on the standard plan.",
            "Rate limit state is returned in the X-RateLimit-Remaining and X-RateLimit-Reset headers.",
            "When you receive a 429, back off until the reset timestamp before retrying.",
            "Batch endpoints let you combine up to 100 operations in a single request.",
            "Enterprise customers can request raised limits through their account manager.",
        ],
    ),
]

TOPIC_BY_NAME = {t.name: t for t in TOPICS}
USER_POOL = [f"user-{i:02d}" for i in range(1, 13)]


@dataclass
class SynthesisParams:
    """Knobs for one synthesized response."""

    quality: float  # target quality 0..1 (ground truth, never written to the record)
    retrieval_relevance: float  # fraction of retrieved snippets from the right doc


@dataclass
class Record:
    idx: int
    ts: str
    stream_id: str
    user_id: str
    topic: str
    difficulty: str
    question: str
    response: str
    reference: str
    snippets: list[dict[str, str]] = field(default_factory=list)
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "idx": self.idx,
            "ts": self.ts,
            "stream_id": self.stream_id,
            "user_id": self.user_id,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "question": self.question,
            "response": self.response,
            "reference": self.reference,
            "snippets": self.snippets,
            "latency_ms": self.latency_ms,
        }


def _decoy_sentences(topic: Topic, rng: random.Random, k: int) -> list[str]:
    others = [s for t in TOPICS if t.name != topic.name for s in t.doc]
    return rng.sample(others, k)


def synthesize_response(topic: Topic, params: SynthesisParams, rng: random.Random) -> str:
    """Turn a target quality + retrieval relevance into actual response text."""
    q = max(0.0, min(1.0, params.quality))
    if q < 0.22 and rng.random() < 0.4:
        return rng.choice(REFUSALS)

    n_total = 4
    n_correct = max(1, round(q * n_total)) if q > 0.12 else 0
    n_correct = min(n_correct, len(topic.doc))
    correct = topic.doc[:n_correct]
    n_wrong = min(n_total - n_correct, 3)
    wrong = _decoy_sentences(topic, rng, n_wrong) if n_wrong > 0 else []

    sentences = correct + wrong
    if not sentences:
        sentences = _decoy_sentences(topic, rng, 2)

    # Hedging grows as quality falls.
    n_hedges = min(len(sentences), max(0, int((0.85 - q) * 6)))
    for i in range(n_hedges):
        s = sentences[i]
        sentences[i] = f"{rng.choice(HEDGES)}, {s[0].lower()}{s[1:]}"

    # Low quality responses sometimes truncate mid-sentence (context cut off).
    if q < 0.5 and rng.random() < 0.5 and sentences:
        last = sentences[-1]
        cut = max(10, int(len(last) * 0.6))
        sentences[-1] = last[:cut].rstrip().rstrip(".,;")

    return " ".join(sentences)


def make_snippets(topic: Topic, params: SynthesisParams, rng: random.Random) -> list[dict]:
    n_total = 4
    n_rel = max(0, min(n_total, round(params.retrieval_relevance * n_total)))
    rel = [{"text": s, "source": topic.name} for s in rng.sample(topic.doc, min(n_rel, len(topic.doc)))]
    dec = [
        {"text": s, "source": "decoy"}
        for s in _decoy_sentences(topic, rng, n_total - len(rel))
    ]
    out = rel + dec
    rng.shuffle(out)
    return out


def make_record(
    idx: int,
    stream_id: str,
    topic: Topic,
    params: SynthesisParams,
    rng: random.Random,
    start: datetime,
    spacing_s: float = 240.0,
) -> Record:
    ts = start + timedelta(seconds=idx * spacing_s + rng.uniform(-30, 30))
    return Record(
        idx=idx,
        ts=ts.isoformat(),
        stream_id=stream_id,
        user_id=rng.choice(USER_POOL),
        topic=topic.name,
        difficulty=topic.difficulty,
        question=rng.choice(topic.questions),
        response=synthesize_response(topic, params, rng),
        reference=" ".join(topic.doc),
        snippets=make_snippets(topic, params, rng),
        latency_ms=max(150.0, rng.gauss(1200.0, 200.0)),
    )


def default_start() -> datetime:
    return datetime(2026, 7, 1, 8, 0, 0, tzinfo=UTC)
