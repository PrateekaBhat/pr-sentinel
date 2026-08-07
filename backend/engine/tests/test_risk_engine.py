from __future__ import annotations

import pytest
from engine.heuristics import analyze, calculate_review_effort
from engine.models import ChangedFile, PullRequestData, RepositoryInfo


def _sample_pr(files: list[ChangedFile]) -> PullRequestData:
    repo = RepositoryInfo(owner="test", name="test", full_name="test/test")
    return PullRequestData(
        owner="test",
        repo="test",
        number=1,
        title="Test PR",
        author="testuser",
        url="https://github.com/test/test/pull/1",
        state="open",
        additions=sum(f.additions for f in files),
        deletions=sum(f.deletions for f in files),
        changed_files_count=len(files),
        files=files,
        repository=repo,
    )


def test_score_math_breakdown():
    files = [
        ChangedFile(
            filename=".github/workflows/ci.yml",
            status="modified",
            additions=15,
            deletions=2,
            changes=17,
        ),
        ChangedFile(
            filename="backend/engine/service.py",
            status="modified",
            additions=100,
            deletions=20,
            changes=120,
        ),
    ]
    pr = _sample_pr(files)
    res = analyze(pr)
    
    # Assert score math contains base risk and triggered rules
    factors = [m.factor for m in res.score_math]
    assert "Base Risk" in factors
    assert "Infrastructure / deployment files changed" in factors
    assert "No test files touched" in factors
    assert res.score == 30  # 20 (infra) + 10 (no_tests)


def test_review_effort_calculation():
    # Small change
    small_files = [ChangedFile(filename="README.md", status="modified", additions=5, deletions=1, changes=6)]
    small_pr = _sample_pr(small_files)
    small_res = analyze(small_pr)
    mins, label = calculate_review_effort(small_pr, small_res)
    assert mins == 5
    assert label == "5 minutes"

    # Large change
    large_files = [
        ChangedFile(filename=f"src/file_{i}.py", status="modified", additions=200, deletions=50, changes=250)
        for i in range(5)
    ]
    large_pr = _sample_pr(large_files)
    large_res = analyze(large_pr)
    mins_l, label_l = calculate_review_effort(large_pr, large_res)
    assert mins_l >= 60
    assert "hour" in label_l
