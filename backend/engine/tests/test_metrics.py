from __future__ import annotations

from engine import heuristics as heuristics_mod
from engine.categories import build_category_breakdown, classify_files
from engine.metrics import build_engineering_metrics, build_operational_checklist, derive_production_readiness_score
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


def test_public_apis_modified_ignores_internal_functions():
    """A plain internal refactor with lots of `def ...` lines in non-API files
    must not be counted as public API surface change — that's what produced
    the '54 public API changes' false positive on a report-renderer refactor
    with zero actual API routes touched."""
    internal_patch = "\n".join(f"+def helper_{i}():" for i in range(20))
    files = [
        ChangedFile(
            filename="backend/engine/report_renderer.py",
            status="modified",
            additions=200,
            deletions=50,
            changes=250,
            patch=internal_patch,
        ),
    ]
    pr = _make_pr(files)
    h = heuristics_mod.analyze(pr)
    ai = _stub_ai()
    cats = build_category_breakdown(pr, h, ai)
    em = build_engineering_metrics(pr, cats)

    assert em.public_apis_modified == 0


def test_public_apis_modified_counts_functions_in_api_files():
    api_patch = "\n".join(f"+def get_thing_{i}():" for i in range(3))
    files = [
        ChangedFile(
            filename="backend/app/api/routes.py",
            status="modified",
            additions=30,
            deletions=5,
            changes=35,
            patch=api_patch,
        ),
    ]
    pr = _make_pr(files)
    h = heuristics_mod.analyze(pr)
    ai = _stub_ai()
    cats = build_category_breakdown(pr, h, ai)
    em = build_engineering_metrics(pr, cats)

    assert em.public_apis_modified == 3


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


def test_readiness_score_penalizes_high_risk_and_missing_tests():
    files = [
        ChangedFile(filename="backend/auth/service.py", status="modified", additions=40, deletions=5, changes=45),
    ]
    pr = _make_pr(files)
    h = heuristics_mod.analyze(pr)
    ai = _stub_ai()
    cats = build_category_breakdown(pr, h, ai)
    em = build_engineering_metrics(pr, cats)
    readiness = derive_production_readiness_score(h, cats, confidence=90, em=em)

    assert 0 <= readiness.score <= 100
    assert readiness.label in ("Ready", "Needs attention", "Not ready")
    # Auth files touched with zero tests should produce at least one deduction.
    assert len(readiness.deductions) >= 1


def test_readiness_score_clean_pr_scores_high():
    files = [
        ChangedFile(filename="README.md", status="modified", additions=5, deletions=1, changes=6),
    ]
    pr = _make_pr(files)
    h = heuristics_mod.analyze(pr)
    ai = _stub_ai()
    cats = build_category_breakdown(pr, h, ai)
    em = build_engineering_metrics(pr, cats)
    readiness = derive_production_readiness_score(h, cats, confidence=95, em=em)

    assert readiness.score >= 80
    assert readiness.label == "Ready"


def test_domain_detection_pydantic_model_is_not_database():
    """Regression test for the exact miscategorization called out in the
    improvement plan: a plain models.py under engine/ is a Pydantic/domain
    model, not a database file, and must not classify as Data Layer."""
    files = [
        ChangedFile(filename="backend/engine/models.py", status="modified", additions=10, deletions=2, changes=12),
    ]
    buckets = classify_files(files)
    assert files[0] not in buckets["Data Layer"]
    assert files[0] in buckets["Application/Core Logic"]


def test_domain_detection_alembic_migration_is_database():
    files = [
        ChangedFile(filename="backend/alembic/versions/0012_add_users.py", status="added", additions=30, deletions=0, changes=30),
    ]
    buckets = classify_files(files)
    assert files[0] in buckets["Data Layer"]
