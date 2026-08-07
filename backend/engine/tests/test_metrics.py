from __future__ import annotations

from engine import heuristics as heuristics_mod
from engine.categories import build_category_breakdown
from engine.metrics import build_engineering_metrics, build_operational_checklist
from engine.models import AIAnalysis, ChangedFile, PullRequestData, RepositoryInfo, RiskLevel


def _stub_ai() -> AIAnalysis:
    return AIAnalysis(
        overall_risk=RiskLevel.LOW,
        confidence=60,
        summary="stub",
        architectural_impact="stub",
        rollout_strategy="Standard",
        rollout_reason="stub",
        rollback_required=False,
    )


def _make_pr(files: list[ChangedFile]) -> PullRequestData:
    return PullRequestData(
        owner="acme",
        repo="widgets",
        number=1,
        title="Test PR",
        author="octocat",
        url="https://github.com/acme/widgets/pull/1",
        state="open",
        additions=sum(f.additions for f in files),
        deletions=sum(f.deletions for f in files),
        changed_files_count=len(files),
        files=files,
        repository=RepositoryInfo(owner="acme", name="widgets", full_name="acme/widgets"),
    )


def test_metrics_counts_workflow_and_config_files():
    files = [
        ChangedFile(filename=".github/workflows/ci.yml", status="modified", additions=5, deletions=1, changes=6),
        ChangedFile(filename="backend/config/settings.py", status="modified", additions=3, deletions=0, changes=3),
        ChangedFile(filename="README.md", status="modified", additions=10, deletions=2, changes=12),
    ]
    pr = _make_pr(files)
    h = heuristics_mod.analyze(pr)
    ai = _stub_ai()
    cats = build_category_breakdown(pr, h, ai)
    em = build_engineering_metrics(pr, cats)

    assert em.workflow_files_changed == 1
    assert em.config_files_changed == 1
    assert em.documentation_files_changed == 1
    assert em.lines_added == 18
    assert em.lines_removed == 3


def test_checklist_includes_ci_task_when_workflow_changed():
    files = [ChangedFile(filename=".github/workflows/ci.yml", status="modified", additions=5, deletions=1, changes=6)]
    pr = _make_pr(files)
    h = heuristics_mod.analyze(pr)
    ai = _stub_ai()
    cats = build_category_breakdown(pr, h, ai)
    em = build_engineering_metrics(pr, cats)
    checklist = build_operational_checklist(cats, h, em)

    tasks = [item.task for item in checklist]
    assert any("CI/CD workflow" in t for t in tasks)
    # Baseline tasks always present.
    assert any("full test suite" in t for t in tasks)
    assert any("rollback plan" in t for t in tasks)


def test_checklist_flags_missing_tests():
    files = [ChangedFile(filename="backend/engine/service.py", status="modified", additions=20, deletions=2, changes=22)]
    pr = _make_pr(files)
    h = heuristics_mod.analyze(pr)
    ai = _stub_ai()
    cats = build_category_breakdown(pr, h, ai)
    em = build_engineering_metrics(pr, cats)
    checklist = build_operational_checklist(cats, h, em)

    assert em.test_files_touched == 0
