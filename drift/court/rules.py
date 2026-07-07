"""The deterministic decision rule over structured evidence.

This is the documented standard of proof. In mock mode the Judge seat applies
it verbatim; in live mode the 235B Judge rules over the same evidence with
this rule stated as the standard, and any unparseable ruling falls back here.
Uncertainty buys evidence, not silence: weak-but-suggestive trends yield WATCH
(tightened sampling), not DISMISS and not ALERT.
"""

from __future__ import annotations

from drift.config import MIN_SAMPLE, TREND_P_ALERT, TREND_P_WATCH, TREND_R2_ALERT

VERDICTS = ("DISMISS", "WATCH", "ALERT")

# Confounders that, when fired, fully explain the decline without degradation.
EXCULPATORY = ("traffic_mix_shift", "outlier_user", "time_of_day", "scorer_noise")


def deterministic_verdict(evidence: dict) -> tuple[str, str]:
    trend = evidence.get("trend") or {}
    confounders = evidence.get("confounders", [])
    fired = {f["name"]: f for f in confounders if f.get("fired")}

    slope = trend.get("slope_per_hour", 0.0)
    p = trend.get("p_value", 1.0)
    r2 = trend.get("r2", 0.0)
    n = trend.get("n", 0)

    for name in EXCULPATORY:
        if name in fired:
            return (
                "DISMISS",
                f"The decline is explained without degradation: {fired[name]['detail']}. "
                "The prosecution's trend does not survive this confounder.",
            )

    suggestive = slope < 0 and p < TREND_P_WATCH

    if "sample_size" in fired:
        if suggestive:
            return (
                "WATCH",
                f"Trend is suggestive (slope {slope:+.4f}/h, p={p:.4g}) but the sample "
                f"is below the conviction minimum ({n} < {MIN_SAMPLE}). Tighten sampling "
                "and re-hear.",
            )
        return ("DISMISS", f"Insufficient sample ({n} rows) and no suggestive trend.")

    if slope < 0 and p < TREND_P_ALERT and r2 >= TREND_R2_ALERT:
        return (
            "ALERT",
            f"Significant decline (slope {slope:+.4f}/h, p={p:.4g}, R2={r2:.2f}, n={n}) "
            "and every confounder on the checklist was tested and cleared.",
        )
    if suggestive:
        return (
            "WATCH",
            f"Decline is suggestive but unproven (slope {slope:+.4f}/h, p={p:.4g}, "
            f"R2={r2:.2f}). Buying evidence: sampling tightens until this is settled.",
        )
    return (
        "DISMISS",
        f"No credible decline (slope {slope:+.4f}/h, p={p:.4g}). Stream is healthy.",
    )
