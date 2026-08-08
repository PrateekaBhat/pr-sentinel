from __future__ import annotations

import pytest

from engine.heuristics import analyze
from engine.models import ChangedFile, PullRequestData, RepositoryInfo
from engine.review_complexity import calculate_review_complexity


def _sample_pr(files: list[ChangedFile], **kwargs) -> PullRequestData:
    repo = RepositoryInfo(owner="test", name="test", full_name="test/test")
    return PullRequestData(
        owner="test",
        repo="test",
        number=1,
        title="Test PR",
        author="testuser",
        url="https://github.com/test/test/pull/1",
        state="open",
        additions=kwargs.get("additions", sum(f.additions for f in files)),
        deletions=kwargs.get("deletions", sum(f.deletions for f in files)),
        changed_files_count=len(files),
        files=files,
        repository=repo,
    )


def test_large_diff_not_in_release_score():
    """Large diffs increase review complexity but must not inflate release risk."""
    files = [
        ChangedFile(
            filename=f"src/module_{i}.py",
            status="modified",
            additions=300,
            deletions=10,
            changes=310,
        )
        for i in range(8)
    ]
    pr = _sample_pr(files, additions=2400, deletions=80)
    hres = analyze(pr)
    complexity = calculate_review_complexity(pr, hres)

    assert hres.score < 30  # no release-risk signals
    assert any(s.key == "large_diff" for s in hres.review_signals)
    assert complexity.level.value == "HIGH"
