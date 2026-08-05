from __future__ import annotations

from typing import Any, TypedDict

from ..models import AgentFinding, AIAnalysis, HeuristicResult, JudgeVerdict, PullRequestData, RAGContext


class AgentState(TypedDict, total=False):
    pr: PullRequestData
    heuristics: HeuristicResult
    rag: RAGContext

    security_finding: AgentFinding
    performance_finding: AgentFinding
    database_finding: AgentFinding
    api_finding: AgentFinding
    tests_finding: AgentFinding

    security_status: dict[str, Any]
    performance_status: dict[str, Any]
    database_status: dict[str, Any]
    api_status: dict[str, Any]
    tests_status: dict[str, Any]

    coordinator_result: AIAnalysis
    coordinator_duration_ms: int
    judge_result: JudgeVerdict
    judge_duration_ms: int
