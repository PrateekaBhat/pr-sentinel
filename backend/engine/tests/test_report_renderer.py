from __future__ import annotations

from engine.models import (
    AgentFinding,
    AIAnalysis,
    AnalyzeResponse,
    ChangedFile,
    FileRisk,
    HeuristicFactor,
    HeuristicResult,
    ProductionReadinessScore,
    PullRequestData,
    RAGChunk,
    RAGContext,
    RepositoryInfo,
    RiskLevel,
    RiskReport,
    RepositoryMetadata,
    ScoreMathFactor,
)
from engine.report_renderer import build_review_queue, render_markdown, _total_review_minutes


def _sample_response(
    files: list[ChangedFile],
    *,
    no_tests: bool = False,
    with_rag: bool = True,
    with_agents: bool = True,
) -> AnalyzeResponse:
    repo = RepositoryInfo(owner="test", name="test", full_name="test/test")
    pr = PullRequestData(
        owner="test",
        repo="test",
        number=3,
        title="Refactor PR Summary report",
        author="dev",
        url="https://github.com/test/test/pull/3",
        state="open",
        additions=sum(f.additions for f in files),
        deletions=sum(f.deletions for f in files),
        changed_files_count=len(files),
        files=files,
        repository=repo,
    )
    factors = []
    if no_tests:
        factors.append(
            HeuristicFactor(key="no_tests", label="No test files touched", triggered=True, weight=10, reason="No tests")
        )
    factors.append(
        HeuristicFactor(key="large_diff", label="Large diff", triggered=True, weight=20, reason="800+ lines")
    )
    heuristics = HeuristicResult(
        score=30,
        factors=factors,
        score_math=[
            ScoreMathFactor(factor="Large diff", points=20, reason="800+ line changes"),
            ScoreMathFactor(factor="Missing tests", points=10, reason="No test files touched"),
        ],
        tests_touched=False,
        tests_deleted=False,
        migration_touched=False,
    )
    file_risks = [
        FileRisk(filename=f.filename, risk=RiskLevel.MEDIUM, reason="Changed")
        for f in files
    ]
    agent_findings = [
        AgentFinding(agent="security", label="Security", applicable=False, risk_note="Skipped"),
        AgentFinding(agent="database", label="Database", applicable=False, risk_note="Skipped"),
        AgentFinding(agent="api", label="API", applicable=False, risk_note="Skipped"),
        AgentFinding(agent="tests", label="Tests", applicable=True, files_reviewed=["backend/engine/report_renderer.py"], findings=["No tests updated"]),
        AgentFinding(agent="performance", label="Performance", applicable=False, risk_note="Skipped"),
    ] if with_agents else []
    report = RiskReport(
        decision="ALLOW",
        risk_score=30,
        confidence=72,
        deployment_strategy="Canary",
        production_readiness=ProductionReadinessScore(score=65, label="Needs attention", deductions=[]),
        repository_metadata=RepositoryMetadata(files_changed_count=len(files)),
    )
    return AnalyzeResponse(
        source="test",
        ai_enabled=True,
        pr=pr,
        heuristics=heuristics,
        ai=AIAnalysis(
            overall_risk=RiskLevel.MEDIUM,
            confidence=72,
            summary="Refactored report rendering.",
            architectural_impact="Report generation updated.",
            operational_risks=[],
            rollout_strategy="Canary",
            rollout_reason="Medium risk change.",
            rollback_required=False,
            file_risks=file_risks,
            agent_findings=agent_findings,
        ),
        rag=RAGContext(
            scanned=with_rag,
            retrieved=[RAGChunk(path="README.md", snippet="Report Generation", score=0.9)] if with_rag else [],
            indexed_doc_paths=["README.md"] if with_rag else [],
        ),
        report=report,
    )


def test_review_queue_ranks_implementation_before_infrastructure():
    files = [
        ChangedFile(filename=".github/workflows/main.yml", status="modified", additions=10, deletions=2, changes=12),
        ChangedFile(filename="backend/engine/report_renderer.py", status="modified", additions=600, deletions=73, changes=673),
        ChangedFile(filename="frontend/src/App.tsx", status="modified", additions=200, deletions=136, changes=336),
    ]
    response = _sample_response(files, no_tests=True)
    queue = build_review_queue(response)
    categories = [item.category for item in queue]
    impl_index = categories.index("implementation")
    infra_index = categories.index("infrastructure")
    assert impl_index < infra_index


def test_review_effort_matches_queue_total():
    files = [
        ChangedFile(filename="backend/engine/report_renderer.py", status="modified", additions=600, deletions=73, changes=673),
        ChangedFile(filename="frontend/src/App.tsx", status="modified", additions=200, deletions=136, changes=336),
        ChangedFile(filename=".github/workflows/main.yml", status="modified", additions=10, deletions=2, changes=12),
    ]
    response = _sample_response(files, no_tests=True)
    queue = build_review_queue(response)
    total = _total_review_minutes(queue)
    markdown = render_markdown(response)
    assert f"**Total review effort:** ~{total} minutes" in markdown or f"**Total review effort:** ~1 hour" in markdown
    assert "Review Queue" in markdown
    assert "Review Priorities" not in markdown
    assert "Review Order" not in markdown


def test_evidence_quality_excludes_regression_tests():
    response = _sample_response(
        [ChangedFile(filename="backend/engine/service.py", status="modified", additions=50, deletions=10, changes=60)],
        no_tests=True,
    )
    markdown = render_markdown(response)
    assert "Deterministic analysis" in markdown
    assert "Git diff" in markdown
    assert "Runtime telemetry" in markdown
    assert "- [ ] Regression tests" not in markdown


def test_why_not_block_for_allow_decision():
    response = _sample_response(
        [ChangedFile(filename="backend/engine/report_renderer.py", status="modified", additions=100, deletions=20, changes=120)],
        no_tests=True,
    )
    markdown = render_markdown(response)
    assert "### Why ALLOW?" in markdown
    assert "No security-sensitive changes" in markdown
    assert "Missing regression coverage" in markdown


def test_risk_breakdown_has_no_percentages():
    response = _sample_response(
        [ChangedFile(filename="backend/engine/report_renderer.py", status="modified", additions=100, deletions=20, changes=120)],
        no_tests=True,
    )
    markdown = render_markdown(response)
    assert "| Share |" not in markdown
    assert "%" not in markdown.split("Risk Contributors")[1].split("Merge Readiness")[0]


def test_coordinator_synthesis_and_repository_coverage():
    response = _sample_response(
        [ChangedFile(filename="backend/engine/report_renderer.py", status="modified", additions=100, deletions=20, changes=120)],
    )
    markdown = render_markdown(response)
    assert "Final synthesis" in markdown
    assert "Coordinator Summary" not in markdown
    assert "Repository coverage:" in markdown
    assert "Repository confidence:" not in markdown


def test_analysis_scope_section():
    response = _sample_response(
        [ChangedFile(filename="backend/engine/report_renderer.py", status="modified", additions=100, deletions=20, changes=120),
         ChangedFile(filename="frontend/src/App.tsx", status="modified", additions=50, deletions=30, changes=80)],
        with_agents=True,
    )
    markdown = render_markdown(response)
    assert "### Analysis Scope" in markdown
    assert "**Files analyzed:** 2 / 2" in markdown
    assert "**Agents executed:** 1" in markdown
    assert "**Agents skipped:** 4" in markdown


def test_review_queue_uses_priority_labels():
    response = _sample_response(
        [ChangedFile(filename="backend/engine/report_renderer.py", status="modified", additions=600, deletions=73, changes=673),
         ChangedFile(filename="frontend/src/App.tsx", status="modified", additions=200, deletions=136, changes=336)],
        no_tests=True,
    )
    markdown = render_markdown(response)
    assert "### 1." in markdown
    assert "Review first" not in markdown
    assert "Review next" not in markdown
