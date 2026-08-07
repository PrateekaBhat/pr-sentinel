from __future__ import annotations

from engine.models import (
    ChangedFile,
    EvidenceItem,
    PullRequestData,
    RepositoryInfo,
    RiskCategory,
    RiskLevel,
)
from engine.reviewers import build_suggested_reviewers


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


def _category(name: str, matched_file: str) -> RiskCategory:
    return RiskCategory(
        category=name,
        score=40,
        status=RiskLevel.MEDIUM,
        evidence=[
            EvidenceItem(
                file_path=matched_file,
                explanation="changed",
                confidence=80,
                severity=RiskLevel.MEDIUM,
                recommended_action="review",
            )
        ],
    )


def test_auth_changes_produce_required_security_reviewer():
    files = [ChangedFile(filename="auth/login.py", status="modified", additions=5, deletions=1, changes=6)]
    pr = _pr(files)
    categories = [_category("Authentication", "auth/login.py")]
    reviewers = build_suggested_reviewers(pr, categories)
    assert any(r.role == "Security Reviewer" and r.required for r in reviewers)
    assert "auth/login.py" in reviewers[0].matched_paths


def test_docs_only_change_has_no_required_reviewer():
    files = [ChangedFile(filename="README.md", status="modified", additions=3, deletions=0, changes=3)]
    pr = _pr(files)
    categories = [_category("Documentation", "README.md")]
    reviewers = build_suggested_reviewers(pr, categories)
    assert all(not r.required for r in reviewers)


def test_frontend_files_get_frontend_reviewer():
    files = [ChangedFile(filename="frontend/src/App.tsx", status="modified", additions=8, deletions=1, changes=9)]
    pr = _pr(files)
    reviewers = build_suggested_reviewers(pr, categories=[])
    assert any(r.role == "Frontend Reviewer" for r in reviewers)


def test_no_matching_categories_produces_empty_list():
    pr = _pr(files=[])
    reviewers = build_suggested_reviewers(pr, categories=[])
    assert reviewers == []


def test_multiple_categories_merge_same_role():
    files = [
        ChangedFile(filename=".env", status="modified", additions=1, deletions=0, changes=1),
        ChangedFile(filename="auth/session.py", status="modified", additions=4, deletions=1, changes=5),
    ]
    pr = _pr(files)
    categories = [
        _category("Secrets", ".env"),
        _category("Authentication", "auth/session.py"),
    ]
    reviewers = build_suggested_reviewers(pr, categories)
    security = [r for r in reviewers if r.role == "Security Reviewer"]
    assert len(security) == 1
    assert set(security[0].matched_paths) == {".env", "auth/session.py"}
