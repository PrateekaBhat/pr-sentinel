from __future__ import annotations

import time
from typing import Any

from . import github_client, heuristics
from .agents.graph import run_pipeline
from .ai_analyzer import analyze_with_heuristics_only
from .config import get_settings
from .github_client import GitHubError
from .models import (
    AIAnalysis,
    AnalyzeResponse,
    AnalyzeRequest,
    AgentStatus,
    HeuristicResult,
    PullRequestData,
    RAGContext,
    RepositoryMetadata,
    RiskFactorFlag,
    RiskReport,
    RiskLevel,
    TimelineStage,
)
from .ollama_client import OllamaError
from .rag.retriever import get_rag_context


def _infer_technologies(files: list[Any]) -> list[str]:
    # Use changed file paths to infer the primary stack touched by this PR.
    tech_tags: set[str] = set()
    patterns = {
        "Docker": ["Dockerfile", "docker/", "docker-compose"],
        "Kubernetes": ["k8s/", "kubernetes/", ".k8s", "helm/"],
        "Terraform": [".tf", "terraform/"],
        "Java": [".java", "pom.xml", "build.gradle", "build.gradle.kts"],
        "Python": [".py", "pyproject.toml", "requirements.txt"],
        "TypeScript": [".ts", ".tsx", "package.json", "tsconfig.json"],
        "Go": [".go", "go.mod"],
        "Node.js": ["package.json", "node_modules"],
    }
    for f in files:
        path = f.filename.lower()
        for label, markers in patterns.items():
            if any(marker in path for marker in markers):
                tech_tags.add(label)
    return sorted(tech_tags)


def _build_risk_breakdown(heuristics: HeuristicResult) -> dict[str, int]:
    category_map = {
        "auth": "Authentication",
        "payment": "Payment",
        "config": "Configuration",
        "infra": "Infrastructure",
        "migration": "Database",
        "api_contract": "API",
        "tests_deleted": "Tests",
        "no_tests": "Tests",
        "large_diff": "Diff size",
        "medium_diff": "Diff size",
    }
    breakdown: dict[str, int] = {}
    for factor in heuristics.factors:
        if not factor.triggered:
            continue
        label = category_map.get(factor.key, factor.label)
        breakdown[label] = breakdown.get(label, 0) + factor.weight
    if not breakdown:
        breakdown["General"] = heuristics.score
    return breakdown


def _build_findings(heuristics: HeuristicResult, ai: AIAnalysis) -> list[str]:
    findings = [factor.label for factor in heuristics.factors if factor.triggered][:5]
    if len(findings) < 5:
        findings.extend([risk.filename for risk in ai.file_risks[: 5 - len(findings)]])
    return findings


def _build_evidence(heuristics: HeuristicResult, ai: AIAnalysis) -> list[str]:
    evidence: list[str] = []
    for factor in heuristics.factors:
        if factor.triggered:
            evidence.append(f"{factor.label}: {factor.reason}")
    for risk in ai.file_risks[:3]:
        evidence.append(f"{risk.filename}: {risk.reason}")
    if not evidence and ai.operational_risks:
        evidence.extend([f"Operational risk: {risk}" for risk in ai.operational_risks[:3]])
    return evidence


def _build_agent_statuses(state: dict[str, Any]) -> list[AgentStatus]:
    statuses: list[AgentStatus] = []
    for domain in ["security", "database", "api", "tests", "performance"]:
        status = state.get(f"{domain}_status")
        if status is None:
            continue
        statuses.append(status)
    return statuses


def _build_timeline(
    repo_loaded_ms: int,
    repo_context_ms: int,
    state: dict[str, Any],
) -> list[TimelineStage]:
    timeline: list[TimelineStage] = [
        TimelineStage(stage="Repository Loaded", duration_ms=repo_loaded_ms),
        TimelineStage(stage="Repository Context Retrieved", duration_ms=repo_context_ms),
    ]
    for domain in ["security", "database", "api", "tests", "performance"]:
        status = state.get(f"{domain}_status")
        if status is None:
            continue
        timeline.append(TimelineStage(stage=status.label, duration_ms=status.duration_ms))
    final_ms = 0
    if state.get("coordinator_duration_ms") is not None:
        final_ms += state["coordinator_duration_ms"]
    if state.get("judge_duration_ms") is not None:
        final_ms += state["judge_duration_ms"]
    if final_ms:
        timeline.append(TimelineStage(stage="Final Decision", duration_ms=final_ms))
    return timeline


def _infer_repository_metadata(pr: PullRequestData, rag: RAGContext) -> RepositoryMetadata:
    return RepositoryMetadata(
        default_branch=rag.default_branch or "main",
        technologies=_infer_technologies(pr.files),
        files_changed_count=pr.changed_files_count,
    )


def _build_report(
    pr: PullRequestData,
    heuristics: HeuristicResult,
    ai: AIAnalysis,
    rag: RAGContext,
    state: dict[str, Any],
    repo_loaded_ms: int,
    repo_context_ms: int,
) -> RiskReport:
    decision = "BLOCK" if ai.overall_risk == RiskLevel.HIGH else "ALLOW"
    return RiskReport(
        decision=decision,
        risk_score=heuristics.score,
        confidence=ai.confidence,
        deployment_strategy=ai.rollout_strategy,
        risk_breakdown=_build_risk_breakdown(heuristics),
        findings=_build_findings(heuristics, ai),
        evidence=_build_evidence(heuristics, ai),
        timeline=_build_timeline(repo_loaded_ms, repo_context_ms, state),
        agent_statuses=_build_agent_statuses(state),
        repository_metadata=_infer_repository_metadata(pr, rag),
    )


def render_comment(response: AnalyzeResponse) -> str:
    findings = response.report.findings or [response.ai.summary]
    details = "\n".join(f"• {item}" for item in findings[:5])
    return (
        "## PR Sentinel Report\n\n"
        f"Overall Risk: {response.ai.overall_risk}\n\n"
        f"Decision: {response.report.decision}\n\n"
        f"Risk Score: {response.report.risk_score} / 100\n\n"
        f"Confidence: {response.ai.confidence}%\n\n"
        "Top Findings\n\n"
        f"{details}\n\n"
        "Recommended Deployment\n\n"
        f"{response.ai.rollout_strategy}\n\n"
        "View Full Report\n"
    )


async def analyze_pr_url(pr_url: str, token: str = "") -> AnalyzeResponse:
    owner, repo, number = github_client.parse_pr_url(pr_url)
    return await analyze_pr(owner, repo, number, token)


async def analyze_pr(owner: str, repo: str, number: int, token: str = "") -> AnalyzeResponse:
    settings = get_settings()
    repo_url = f"https://github.com/{owner}/{repo}/pull/{number}"
    start = time.perf_counter_ns()
    settings = get_settings()
    token = token or settings.github_token
    pr = await github_client.fetch_pull_request(owner, repo, number, token=token)
    repo_loaded_ms = int((time.perf_counter_ns() - start) / 1_000_000)

    try:
        rag_context = await get_rag_context(pr, token=token)
    except Exception as exc:  # noqa: BLE001
        rag_context = RAGContext(scanned=False, skip_reason="RAG retrieval failed unexpectedly.")

    repo_context_ms = int((time.perf_counter_ns() - start) / 1_000_000) - repo_loaded_ms

    heuristic_result = heuristics.analyze(pr)
    ai_enabled = True
    ai_error: str | None = None
    judge_result = None
    state: dict[str, Any] = {}
    try:
        state = await run_pipeline(pr, heuristic_result, rag_context)
        ai_result = state["coordinator_result"]
        judge_result = state.get("judge_result")
    except OllamaError as exc:
        ai_enabled = False
        ai_error = str(exc)
        ai_result = analyze_with_heuristics_only(pr, heuristic_result, reason=str(exc))
    except Exception as exc:  # noqa: BLE001
        ai_enabled = False
        ai_error = f"Unexpected error running the agent pipeline: {exc}"
        ai_result = analyze_with_heuristics_only(pr, heuristic_result, reason=ai_error)

    report = _build_report(pr, heuristic_result, ai_result, rag_context, state, repo_loaded_ms, repo_context_ms)
    response = AnalyzeResponse(
        pr=pr,
        heuristics=heuristic_result,
        ai=ai_result,
        report=report,
        ai_enabled=ai_enabled,
        ai_error=ai_error,
        rag=rag_context,
        judge=judge_result,
        source="live",
    )
    return response


async def analyze_request(request: AnalyzeRequest, token: str = "") -> AnalyzeResponse:
    return await analyze_pr_url(request.pr_url, token=token)
