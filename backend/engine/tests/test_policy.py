from __future__ import annotations

import pytest

from engine.models import RiskLevel, ReleaseDecision
from engine.policy import (
    RELEASE_RISK_HIGH_THRESHOLD,
    RELEASE_RISK_MEDIUM_THRESHOLD,
    audit_llm_disagreement,
    classify_release_risk,
    decide_release,
    evaluate_policy,
)


@pytest.mark.parametrize(
    "score,expected_risk,expected_decision",
    [
        (0, RiskLevel.LOW, ReleaseDecision.ALLOW),
        (29, RiskLevel.LOW, ReleaseDecision.ALLOW),
        (30, RiskLevel.MEDIUM, ReleaseDecision.NEEDS_REVIEW),
        (59, RiskLevel.MEDIUM, ReleaseDecision.NEEDS_REVIEW),
        (60, RiskLevel.HIGH, ReleaseDecision.BLOCK),
        (100, RiskLevel.HIGH, ReleaseDecision.BLOCK),
    ],
)
def test_policy_boundaries(score, expected_risk, expected_decision):
    risk = classify_release_risk(score)
    decision = decide_release(risk)
    assert risk == expected_risk
    assert decision == expected_decision
    assert evaluate_policy(score) == (expected_risk, expected_decision)


def test_threshold_constants():
    assert RELEASE_RISK_MEDIUM_THRESHOLD == 30
    assert RELEASE_RISK_HIGH_THRESHOLD == 60


def test_optimistic_llm_disagreement():
    result = audit_llm_disagreement(RiskLevel.HIGH, RiskLevel.LOW, ai_enabled=True)
    assert result.detected is True
    assert result.direction == "optimistic"
    assert result.final_risk == RiskLevel.HIGH
    assert decide_release(result.final_risk) == ReleaseDecision.BLOCK


def test_pessimistic_llm_disagreement():
    result = audit_llm_disagreement(RiskLevel.LOW, RiskLevel.HIGH, ai_enabled=True)
    assert result.detected is True
    assert result.direction == "pessimistic"
    assert result.final_risk == RiskLevel.LOW
    assert decide_release(result.final_risk) == ReleaseDecision.ALLOW


def test_no_disagreement_when_agreement():
    result = audit_llm_disagreement(RiskLevel.MEDIUM, RiskLevel.MEDIUM, ai_enabled=True)
    assert result.detected is False
    assert result.direction is None


def test_no_disagreement_when_ai_unavailable():
    result = audit_llm_disagreement(RiskLevel.HIGH, None, ai_enabled=False)
    assert result.detected is False
    assert result.final_risk == RiskLevel.HIGH
