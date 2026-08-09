"""Golden architecture tests — verify deterministic policy, routing, and separation of concerns."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from engine import agent_routing, heuristics as heuristics_mod
from engine.ai_analyzer import analyze_with_heuristics_only
from engine.categories import build_specialist_routing
from engine.models import (
    ChangedFile,
    HeuristicResult,
    PullRequestData,
    RAGContext,
    ReleaseDecision,
    RepositoryInfo,
    RiskLevel,
)
from engine.policy import audit_llm_disagreement, decide_release, evaluate_policy
from engine.review_complexity import calculate_review_complexity
from engine.service import _build_report


def _repo() -> RepositoryInfo:
    return RepositoryInfo(owner="test", name="test", full_name="test/test")


def _pr(files: list[ChangedFile], **kwargs) -> PullRequestData:
    additions = kwargs.pop("additions", sum(f.additions for f in files))
    deletions = kwargs.pop("deletions", sum(f.deletions for f in files))
    return PullRequestData(
        owner="test",
        repo="test",
        number=1,
        title=kwargs.pop("title", "Test PR"),
        author="dev",
        url="https://github.com/test/test/pull/1",
        state="open",
        additions=additions,
        deletions=deletions,
        changed_files_count=len(files),
        files=files,
        repository=_repo(),
        **kwargs,
    )


def _file(path: str, *, adds: int = 10, dels: int = 2, status: str = "modified") -> ChangedFile:
    return ChangedFile(
        filename=path,
        status=status,
        additions=adds,
        deletions=dels,
        changes=adds + dels,
    )


def _routing_status(pr: PullRequestData, heuristics: HeuristicResult) -> dict:
    """Simulate agent graph state without LLM calls."""
    state: dict = {}
    for domain in ["security", "database", "api", "tests", "performance"]:
        files = agent_routing.files_for_domain(pr.files, domain)
        if files:
            state[f"{domain}_finding"] = type("F", (), {"applicable": True, "findings": [], "risk_note": "", "confidence": 70})()
            state[f"{domain}_status"] = {
                "agent": domain,
                "label": agent_routing.DOMAIN_LABELS[domain],
                "status": "Completed",
                "files_reviewed": len(files),
                "duration_ms": 100,
            }
        else:
            state[f"{domain}_finding"] = type("F", (), {"applicable": False, "findings": [], "risk_note": "skipped", "confidence": 100})()
            state[f"{domain}_status"] = {
                "agent": domain,
                "label": agent_routing.DOMAIN_LABELS[domain],
                "status": "Skipped",
                "files_reviewed": 0,
                "duration_ms": 0,
            }
    return state


def _domain_status(routing, domain: str) -> str:
    entry = next(r for r in routing if r.domain == domain)
    return entry.status


# --- Test 1: Critical Auth Refactor -------------------------------------------------

def test_critical_auth_refactor():
    files = [
        _file("auth/session.py", adds=80, dels=40),
        _file("auth/middleware.py", adds=50, dels=30),
        _file("routes/api.py", adds=10, dels=5),
        _file("tests/test_session.py", adds=0, dels=40, status="removed"),
    ]
    pr = _pr(files)
    hres = heuristics_mod.analyze(pr)

    risk, decision = evaluate_policy(hres.score)
    routing = build_specialist_routing(_routing_status(pr, hres), pr)

    assert risk == RiskLevel.HIGH
    assert decision == ReleaseDecision.BLOCK
    assert _domain_status(routing, "security") == "EXECUTED"


# --- Test 2: Database Migration -----------------------------------------------------

def test_database_migration():
    files = [
        _file("migrations/0042_add_column.sql", adds=20, dels=0, status="added"),
        _file("schema.sql", adds=2, dels=2),
    ]
    pr = _pr(files)
    hres = heuristics_mod.analyze(pr)
    risk, decision = evaluate_policy(hres.score)
    routing = build_specialist_routing(_routing_status(pr, hres), pr)

    assert _domain_status(routing, "database") == "EXECUTED"
    assert _domain_status(routing, "security") == "SKIPPED"
    assert risk in (RiskLevel.MEDIUM, RiskLevel.HIGH)
    assert decision in (ReleaseDecision.NEEDS_REVIEW, ReleaseDecision.BLOCK)


# --- Test 3: Routine Backend Refactor -----------------------------------------------

def test_routine_backend_refactor():
    files = [
        _file("backend/engine/service.py", adds=40, dels=10),
        _file("backend/engine/tests/test_service.py", adds=30, dels=5),
    ]
    pr = _pr(files)
    hres = heuristics_mod.analyze(pr)
    risk, decision = evaluate_policy(hres.score)
    routing = build_specialist_routing(_routing_status(pr, hres), pr)

    assert risk == RiskLevel.LOW
    assert decision == ReleaseDecision.ALLOW
    assert _domain_status(routing, "security") == "SKIPPED"
    assert _domain_status(routing, "database") == "SKIPPED"


# --- Test 4: Docs Only ----------------------------------------------------------------

def test_docs_only():
    files = [
        _file("docs/getting-started.md", adds=100, dels=20),
        _file("README.md", adds=30, dels=10),
    ]
    pr = _pr(files)
    hres = heuristics_mod.analyze(pr)
    risk, decision = evaluate_policy(hres.score)
    routing = build_specialist_routing(_routing_status(pr, hres), pr)

    assert risk == RiskLevel.LOW
    assert decision == ReleaseDecision.ALLOW
    assert all(r.status == "SKIPPED" for r in routing if r.domain != "tests")


# --- Test 5: Large Diff Separation (MANDATORY) ----------------------------------------

def test_large_diff_separation():
    files = [
        ChangedFile(
            filename=f"backend/module/file_{i}.py",
            status="modified",
            additions=250,
            deletions=10,
            changes=260,
        )
        for i in range(8)
    ] + [
        ChangedFile(
            filename=f"backend/tests/test_file_{i}.py",
            status="modified",
            additions=20,
            deletions=5,
            changes=25,
        )
        for i in range(2)
    ]
    pr = _pr(files, additions=2060, deletions=90)
    hres = heuristics_mod.analyze(pr)
    complexity = calculate_review_complexity(pr, hres)
    risk, decision = evaluate_policy(hres.score)

    assert risk == RiskLevel.LOW, f"release score was {hres.score}, expected LOW release risk"
    assert complexity.level == RiskLevel.HIGH
    assert decision == ReleaseDecision.ALLOW


# --- Test 6: Optimistic LLM -----------------------------------------------------------

def test_optimistic_llm_override():
    disagreement = audit_llm_disagreement(RiskLevel.HIGH, RiskLevel.LOW, ai_enabled=True)
    assert disagreement.detected
    assert disagreement.direction == "optimistic"
    assert disagreement.final_risk == RiskLevel.HIGH
    assert decide_release(disagreement.final_risk) == ReleaseDecision.BLOCK


# --- Test 7: Pessimistic LLM ----------------------------------------------------------

def test_pessimistic_llm_override():
    disagreement = audit_llm_disagreement(RiskLevel.LOW, RiskLevel.HIGH, ai_enabled=True)
    assert disagreement.detected
    assert disagreement.direction == "pessimistic"
    assert disagreement.final_risk == RiskLevel.LOW
    assert decide_release(disagreement.final_risk) == ReleaseDecision.ALLOW


# --- Test 8: Multi-Domain PR ----------------------------------------------------------

def test_multi_domain_routing():
    files = [
        _file("auth/login.py", adds=30, dels=10),
        _file("migrations/001.sql", adds=15, dels=0, status="added"),
        _file("tests/test_auth.py", adds=40, dels=5),
    ]
    pr = _pr(files)
    hres = heuristics_mod.analyze(pr)
    routing = build_specialist_routing(_routing_status(pr, hres), pr)

    assert _domain_status(routing, "security") == "EXECUTED"
    assert _domain_status(routing, "database") == "EXECUTED"
    assert _domain_status(routing, "tests") == "EXECUTED"
    assert evaluate_policy(hres.score)[0] == RiskLevel.HIGH


# --- Test 9: LLM Provider Failure -----------------------------------------------------

def test_llm_outage_resilience():
    files = [_file("backend/worker.py", adds=20, dels=5)]
    pr = _pr(files)
    hres = heuristics_mod.analyze(pr)

    ai = analyze_with_heuristics_only(pr, hres, reason="Ollama unavailable")
    report = _build_report(
        pr,
        hres,
        ai,
        rag=RAGContext(scanned=False),
        state={},
        repo_loaded_ms=10,
        repo_context_ms=5,
        ai_enabled=False,
        judge=None,
        total_duration_ms=20,
    )

    assert report.decision == ReleaseDecision.ALLOW.value
    assert report.release_risk == RiskLevel.LOW
    assert report.execution_metrics is not None
    assert report.execution_metrics.ai_enabled is False
