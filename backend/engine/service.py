from __future__ import annotations

import time
from typing import Any

from . import github_client
from . import heuristics as heuristics_mod
from .agents.graph import run_pipeline
from .ai_analyzer import analyze_with_heuristics_only
from .categories import (
    build_agent_decisions,
    build_architectural_impact,
    build_category_breakdown,
    build_confidence_explanation,
    build_specialist_routing,
    reconcile_executive_summary,
)
from .config import get_settings
from .github_client import GitHubError
from . import history
from .metrics import build_engineering_metrics, build_operational_checklist, derive_production_readiness_score
from .policy import audit_llm_disagreement, evaluate_policy
from .review_complexity import calculate_review_complexity
from .review_queue import build_review_queue
from .reviewers import build_suggested_reviewers
from .evidence_gaps import build_positive_signals, build_uncertainties
from datetime import datetime, timezone

from .models import (
    AIAnalysis,
    AnalyzeResponse,
    AnalyzeRequest,
    AgentStatus,
    DeploymentRecommendation,
    ExecutionMetrics,
    HeuristicResult,
    JudgeVerdict,
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
from .report_renderer import render_markdown


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
        "api_client": "API",
        "tests_deleted": "Tests",
        "no_tests": "Tests",
        "large_diff": "Review surface",
        "medium_diff": "Review surface",
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
    for signal in heuristics.review_signals:
        if signal.triggered:
            evidence.append(f"[Review complexity] {signal.label}: {signal.reason}")
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
        label = status["label"] if isinstance(status, dict) else status.label
        duration = status["duration_ms"] if isinstance(status, dict) else status.duration_ms
        timeline.append(TimelineStage(stage=label, duration_ms=duration))
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


_DEPLOYMENT_ALTERNATIVES = {
    "Standard": ["Canary (unnecessary — low measured risk)", "Manual Approval (unnecessary overhead for this change)"],
    "Canary": ["Standard (skipped — this touches a live code path)", "Blue/Green (more than this change warrants)"],
    "Blue/Green": ["Canary (insufficient isolation for an infra/schema change)", "Standard (too risky to ship all-at-once)"],
    "Manual Approval": ["Canary (not sufficient given the sensitivity of what changed)", "Standard (too risky without human sign-off)"],
}


def _build_report(
    pr: PullRequestData,
    heuristics: HeuristicResult,
    ai: AIAnalysis,
    rag: RAGContext,
    state: dict[str, Any],
    repo_loaded_ms: int,
    repo_context_ms: int,
    ai_enabled: bool,
    judge: JudgeVerdict | None,
    total_duration_ms: int,
) -> RiskReport:
    release_risk, release_decision = evaluate_policy(heuristics.score)
    decision = release_decision.value

    llm_risk = ai.overall_risk if ai_enabled else None
    disagreement = audit_llm_disagreement(release_risk, llm_risk, ai_enabled=ai_enabled)

    review_complexity = calculate_review_complexity(pr, heuristics)
    review_queue = build_review_queue(pr, heuristics)
    specialist_routing = build_specialist_routing(state, pr) if state else []

    category_breakdown = build_category_breakdown(pr, heuristics, ai)
    architectural_impact = build_architectural_impact(pr, category_breakdown, ai)
    confidence_explanation = build_confidence_explanation(
        heuristics,
        ai,
        rag,
        ai_enabled,
        judge.grounded if judge else None,
        llm_disagreement_detected=disagreement.detected,
    )
    effort_minutes, effort_label = heuristics_mod.calculate_review_effort(pr, heuristics)

    # Rollout metadata mapping per strategy
    monitoring_map = {
        "Canary": "Monitor CI pipeline step completion, runner resource usage, and error rate during early deployment.",
        "Standard": "Standard telemetry monitoring; verify post-merge automated build checks.",
        "Blue/Green": "Monitor database connection pools, migration lock times, and API error rates on green environment.",
        "Manual Approval": "Verify staging environment end-to-end integration tests before manual production promotion.",
    }
    rollback_map = {
        "Canary": "Immediate rollback on any pipeline failure or unexpected workflow runner exit code.",
        "Standard": "Standard git revert if post-merge production regression is detected.",
        "Blue/Green": "Instant traffic switch back to blue environment if green telemetry degrades.",
        "Manual Approval": "Revert commit and restore database snapshot if schema migration fails.",
    }
    approval_map = {
        "Canary": "Platform / DevOps Lead",
        "Standard": "Peer Code Reviewer",
        "Blue/Green": "Lead Backend & SRE Engineer",
        "Manual Approval": "Staff Security & Infrastructure Code Owner",
    }

    deployment_recommendation = DeploymentRecommendation(
        strategy=ai.rollout_strategy,
        reason=ai.rollout_reason,
        monitoring_focus=monitoring_map.get(ai.rollout_strategy, "Monitor error rates and service latency post-merge."),
        rollback_trigger=rollback_map.get(ai.rollout_strategy, "Revert pull request if production telemetry degrades."),
        approval_level=approval_map.get(ai.rollout_strategy, "Standard Peer Review"),
        alternatives_considered=_DEPLOYMENT_ALTERNATIVES.get(ai.rollout_strategy, []),
        rollback_required=ai.rollback_required,
    )

    engineering_metrics = build_engineering_metrics(pr, category_breakdown)
    operational_checklist = build_operational_checklist(category_breakdown, heuristics, engineering_metrics)
    production_readiness = derive_production_readiness_score(
        heuristics, category_breakdown, confidence_explanation.score, engineering_metrics
    )
    suggested_reviewers = build_suggested_reviewers(pr, category_breakdown)
    positive_signals = build_positive_signals(heuristics)
    uncertainties = build_uncertainties(pr, heuristics, ai, rag, category_breakdown)

    # Tier-1 main concern from deterministic signals + review complexity
    triggered = [f for f in heuristics.factors if f.triggered]
    if triggered:
        main_concern = triggered[0].label
    elif review_complexity.level == RiskLevel.HIGH:
        main_concern = "Large change surface requires focused review"
    else:
        main_concern = "No high-severity release-risk signals detected"

    exec_summary = ai.executive_summary or ai.summary
    if not ai_enabled:
        exec_summary = (
            "AI synthesis unavailable. Final release decision was produced by the deterministic policy engine. "
            + exec_summary
        )

    agent_decisions = build_agent_decisions(state)
    needs_verification: list[str] = []
    for f in ai.agent_findings:
        for lv in f.needs_verification:
            needs_verification.append(f"{f.label}: {lv.title}")
    # Belt-and-suspenders: the coordinator already reconciles the executive summary
    # against agent findings before the judge sees it (agents/nodes.py), so this call
    # is normally a no-op. It stays here as a safety net for the ai_enabled=False path
    # and any future callers that bypass the coordinator. Idempotent by construction.
    exec_summary = reconcile_executive_summary(exec_summary, ai.agent_findings)

    return RiskReport(
        decision=decision,
        release_risk=release_risk,
        review_complexity=review_complexity,
        llm_disagreement=disagreement,
        specialist_routing=specialist_routing,
        review_queue=review_queue,
        risk_score=heuristics.score,
        confidence=confidence_explanation.score,
        review_effort_minutes=effort_minutes,
        review_effort_label=effort_label,
        deployment_strategy=ai.rollout_strategy,
        score_math=heuristics.score_math,
        risk_breakdown=_build_risk_breakdown(heuristics),
        risk_categories=category_breakdown,
        findings=_build_findings(heuristics, ai),
        evidence=_build_evidence(heuristics, ai),
        timeline=_build_timeline(repo_loaded_ms, repo_context_ms, state),
        agent_statuses=_build_agent_statuses(state),
        agent_decisions=agent_decisions,
        repository_metadata=_infer_repository_metadata(pr, rag),
        summary=ai.summary,
        executive_summary=exec_summary,
        architectural_impact=architectural_impact,
        confidence_explanation=confidence_explanation,
        deployment_recommendation=deployment_recommendation,
        engineering_metrics=engineering_metrics,
        operational_checklist=operational_checklist,
        production_readiness=production_readiness,
        suggested_reviewers=suggested_reviewers,
        positive_signals=positive_signals,
        uncertainties=uncertainties,
        needs_verification=needs_verification,
        execution_metrics=ExecutionMetrics(
            generated_at=datetime.now(timezone.utc).isoformat(),
            total_duration_ms=total_duration_ms,
            ai_enabled=ai_enabled,
            rag_cache_hit=rag.cache_hit,
        ),
    )


def render_comment(response: AnalyzeResponse) -> str:
    """Polished Markdown suitable for posting as a GitHub PR comment."""
    return render_markdown(response)


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

    heuristic_result = heuristics_mod.analyze(pr)
    ai_enabled = True
    ai_error: str | None = None
    judge_result = None
    state: dict[str, Any] = {}
    try:
        state = await run_pipeline(pr, heuristic_result, rag_context)
        ai_result = state.get("coordinator_result")
        judge_result = state.get("judge_result")
        if ai_result is None:
            # Coordinator failed gracefully (see coordinator_node) — specialist agent
            # findings/timing in `state` are still real and get reflected in the report.
            ai_enabled = False
            ai_error = state.get("coordinator_error") or "Coordinator did not produce a result."
            ai_result = analyze_with_heuristics_only(pr, heuristic_result, reason=ai_error)
    except OllamaError as exc:
        ai_enabled = False
        ai_error = str(exc)
        ai_result = analyze_with_heuristics_only(pr, heuristic_result, reason=str(exc))
    except Exception as exc:  # noqa: BLE001
        ai_enabled = False
        ai_error = f"Unexpected error running the agent pipeline: {exc}"
        ai_result = analyze_with_heuristics_only(pr, heuristic_result, reason=ai_error)

    total_duration_ms = int((time.perf_counter_ns() - start) / 1_000_000)
    report = _build_report(
        pr, heuristic_result, ai_result, rag_context, state,
        repo_loaded_ms, repo_context_ms, ai_enabled, judge_result,
        total_duration_ms,
    )
    policy_note = ""
    if not ai_enabled:
        policy_note = (
            "AI synthesis unavailable. Final release decision was produced by the deterministic policy engine."
        )

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
        policy_note=policy_note,
    )
    try:
        history.record_analysis(response)
    except Exception:  # noqa: BLE001 — history is best-effort, never blocks the response
        pass
    return response


async def analyze_request(request: AnalyzeRequest, token: str = "") -> AnalyzeResponse:
    return await analyze_pr_url(request.pr_url, token=token)
