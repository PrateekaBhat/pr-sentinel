from __future__ import annotations

from engine.evidence_gaps import build_positive_signals, build_uncertainties
from engine.models import (
    AIAnalysis,
    ChangedFile,
    EvidenceItem,
    PullRequestData,
    RAGContext,
    RepositoryInfo,
    RiskCategory,
    RiskLevel,
)
from engine import heuristics


def _pr(files: list[ChangedFile]) -> PullRequestData:
    return PullRequestData(
        owner="acme",
        repo="widgets",
        number=1,
        title="test pr",
        author="octocat",
        url="https://github.com/acme/widgets/pull/1",
        state="open",
        additions=10,
        deletions=2,
        changed_files_count=len(files),
        files=files,
        repository=RepositoryInfo(owner="acme", name="widgets", full_name="acme/widgets"),
    )


def _ai(**overrides) -> AIAnalysis:
    base = dict(
        overall_risk=RiskLevel.LOW,
        confidence=80,
        summary="s",
        architectural_impact="a",
        rollout_strategy="Standard",
        rollout_reason="r",
        rollback_required=False,
    )
    base.update(overrides)
    return AIAnalysis(**base)


def test_docs_only_pr_has_multiple_positive_signals():
    files = [ChangedFile(filename="README.md", status="modified", additions=3, deletions=0, changes=3)]
    pr = _pr(files)
    result = heuristics.analyze(pr)
    signals = build_positive_signals(result)
    labels = {s.label for s in signals}
    assert "No authentication logic touched" in labels
    assert "No database migration detected" in labels
    assert "No test files were deleted" in labels


def test_auth_change_does_not_produce_no_auth_signal():
    files = [ChangedFile(filename="auth/login.py", status="modified", additions=5, deletions=1, changes=6)]
    pr = _pr(files)
    result = heuristics.analyze(pr)
    signals = build_positive_signals(result)
    labels = {s.label for s in signals}
    assert "No authentication logic touched" not in labels


def test_unscanned_rag_produces_uncertainty():
    pr = _pr([])
    result = heuristics.analyze(pr)
    ai = _ai(test_coverage_estimate_pct=90)
    rag = RAGContext(scanned=False, skip_reason="Embedding model unavailable")
    items = build_uncertainties(pr, result, ai, rag, categories=[])
    areas = {i.area for i in items}
    assert "Repository documentation context" in areas


def test_missing_coverage_estimate_produces_uncertainty():
    pr = _pr([])
    result = heuristics.analyze(pr)
    ai = _ai(test_coverage_estimate_pct=None)
    rag = RAGContext(scanned=True)
    items = build_uncertainties(pr, result, ai, rag, categories=[])
    areas = {i.area for i in items}
    assert "Test coverage impact" in areas


def test_migration_without_rollback_evidence_flags_uncertainty():
    files = [ChangedFile(filename="alembic/versions/0001_x.py", status="added", additions=20, deletions=0, changes=20)]
    pr = _pr(files)
    result = heuristics.analyze(pr)
    ai = _ai(test_coverage_estimate_pct=90)
    rag = RAGContext(scanned=True)
    data_layer = RiskCategory(
        category="Data Layer",
        score=35,
        status=RiskLevel.MEDIUM,
        evidence=[
            EvidenceItem(
                file_path="alembic/versions/0001_x.py",
                explanation="migration",
                confidence=80,
                severity=RiskLevel.MEDIUM,
                recommended_action="review",
            )
        ],
    )
    items = build_uncertainties(pr, result, ai, rag, categories=[data_layer])
    areas = {i.area for i in items}
    assert "Migration backward-compatibility" in areas


def test_fully_evidenced_pr_produces_no_uncertainties():
    files = [
        ChangedFile(filename="benchmark/load_test.py", status="modified", additions=5, deletions=1, changes=6),
    ]
    pr = _pr(files)
    result = heuristics.analyze(pr)
    ai = _ai(test_coverage_estimate_pct=95)
    rag = RAGContext(scanned=True)
    items = build_uncertainties(pr, result, ai, rag, categories=[])
    assert items == []
