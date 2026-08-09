"""Enrich analyze responses with policy fields — used for demo payloads and backfill."""

from __future__ import annotations

from .categories import build_specialist_routing
from .models import AnalyzeResponse, RiskLevel
from .policy import audit_llm_disagreement, evaluate_policy
from .review_complexity import calculate_review_complexity
from .review_queue import build_review_queue


def enrich_analyze_response(response: AnalyzeResponse, state: dict | None = None) -> AnalyzeResponse:
    """Apply deterministic policy and derived fields to a response payload."""
    pr = response.pr
    heuristics = response.heuristics
    ai = response.ai
    report = response.report

    release_risk, release_decision = evaluate_policy(heuristics.score)
    disagreement = audit_llm_disagreement(
        release_risk,
        ai.overall_risk if response.ai_enabled else None,
        ai_enabled=response.ai_enabled,
    )
    review_complexity = calculate_review_complexity(pr, heuristics)
    review_queue = build_review_queue(pr, heuristics)
    routing = build_specialist_routing(state or _state_from_demo(response), pr)

    policy_note = response.policy_note
    if not response.ai_enabled and not policy_note:
        policy_note = (
            "AI synthesis unavailable. Final release decision was produced by the deterministic policy engine."
        )

    updated_report = report.model_copy(
        update={
            "decision": release_decision.value,
            "release_risk": release_risk,
            "review_complexity": review_complexity,
            "llm_disagreement": disagreement,
            "specialist_routing": routing,
            "review_queue": review_queue,
            "risk_score": heuristics.score,
        }
    )

    return response.model_copy(update={"report": updated_report, "policy_note": policy_note})


def _state_from_demo(response: AnalyzeResponse) -> dict:
    """Reconstruct minimal agent state from demo agent_statuses / agent_findings."""
    state: dict = {}
    for finding in response.ai.agent_findings:
        domain = finding.agent
        status_row = next((s for s in response.report.agent_statuses if s.agent == domain), None)
        state[f"{domain}_finding"] = finding
        if status_row:
            state[f"{domain}_status"] = {
                "agent": domain,
                "label": status_row.label,
                "status": status_row.status,
                "files_reviewed": status_row.files_reviewed,
                "duration_ms": status_row.duration_ms,
            }
    return state
