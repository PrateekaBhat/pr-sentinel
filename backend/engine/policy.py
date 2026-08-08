"""Deterministic release policy — the authoritative source for release decisions.

The LLM may analyze and explain evidence, but this module owns the final
release decision. All API responses, reports, and UI must use these functions.
"""

from __future__ import annotations

from enum import Enum

from .models import LLMDisagreement, RiskLevel


class ReleaseDecision(str, Enum):
    ALLOW = "ALLOW"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCK = "BLOCK"


# Authoritative thresholds — do not duplicate elsewhere.
RELEASE_RISK_HIGH_THRESHOLD = 60
RELEASE_RISK_MEDIUM_THRESHOLD = 30


def classify_release_risk(score: int) -> RiskLevel:
    """Map the deterministic heuristic score to a release-risk band."""
    if score >= RELEASE_RISK_HIGH_THRESHOLD:
        return RiskLevel.HIGH
    if score >= RELEASE_RISK_MEDIUM_THRESHOLD:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def decide_release(risk: RiskLevel) -> ReleaseDecision:
    """Map release risk to the final merge/release decision."""
    if risk == RiskLevel.HIGH:
        return ReleaseDecision.BLOCK
    if risk == RiskLevel.MEDIUM:
        return ReleaseDecision.NEEDS_REVIEW
    return ReleaseDecision.ALLOW


def evaluate_policy(heuristic_score: int) -> tuple[RiskLevel, ReleaseDecision]:
    """Single entry point for deterministic policy evaluation."""
    risk = classify_release_risk(heuristic_score)
    return risk, decide_release(risk)


_RISK_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}


def audit_llm_disagreement(
    deterministic_risk: RiskLevel,
    llm_risk: RiskLevel | None,
    *,
    ai_enabled: bool,
) -> LLMDisagreement:
    """Detect when the LLM assessment diverges from deterministic policy.

    Deterministic policy always wins — this records the disagreement for audit.
    """
    if not ai_enabled or llm_risk is None:
        return LLMDisagreement(
            detected=False,
            deterministic_risk=deterministic_risk,
            llm_risk=llm_risk,
            final_risk=deterministic_risk,
            direction=None,
            reason="No LLM assessment available; deterministic policy is authoritative.",
        )

    if llm_risk == deterministic_risk:
        return LLMDisagreement(
            detected=False,
            deterministic_risk=deterministic_risk,
            llm_risk=llm_risk,
            final_risk=deterministic_risk,
            direction=None,
            reason="LLM assessment agrees with deterministic release-risk classification.",
        )

    det_rank = _RISK_ORDER[deterministic_risk]
    llm_rank = _RISK_ORDER[llm_risk]

    if llm_rank < det_rank:
        direction = "optimistic"
        reason = (
            f"LLM assessed {llm_risk.value} release risk while deterministic policy "
            f"classified {deterministic_risk.value}. Final decision follows deterministic override."
        )
    else:
        direction = "pessimistic"
        reason = (
            f"LLM assessed {llm_risk.value} release risk while deterministic policy "
            f"classified {deterministic_risk.value}. Final decision follows deterministic override."
        )

    return LLMDisagreement(
        detected=True,
        deterministic_risk=deterministic_risk,
        llm_risk=llm_risk,
        final_risk=deterministic_risk,
        direction=direction,
        reason=reason,
    )
