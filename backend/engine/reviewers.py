from __future__ import annotations

import re

from .models import PullRequestData, RiskCategory, SuggestedReviewer

# Maps the fixed category taxonomy (see categories.py) onto the role that would
# own a review of that area. This is a deterministic stand-in for a CODEOWNERS
# file: PR Sentinel has no access to org membership, so it recommends a role,
# not a named person.
_CATEGORY_TO_ROLE: dict[str, tuple[str, bool]] = {
    # category -> (role label, required)
    "Authentication": ("Security Reviewer", True),
    "Secrets": ("Security Reviewer", True),
    "Data Layer": ("Database / Backend Reviewer", True),
    "Infrastructure": ("Platform / DevOps Reviewer", False),
    "CI/CD": ("Platform / DevOps Reviewer", False),
    "API": ("Backend / API Reviewer", False),
    "Dependencies": ("Backend Reviewer", False),
    "Tests": ("QA Reviewer", False),
    "Application/Core Logic": ("Backend Reviewer", False),
    "Documentation": ("Docs Reviewer", False),
}

_FRONTEND_RE = re.compile(
    r"(^|/)frontend(/|\.)|\.(tsx|jsx|css|scss)$|(^|/)components?(/|\.)",
    re.I,
)


def build_suggested_reviewers(
    pr: PullRequestData, categories: list[RiskCategory]
) -> list[SuggestedReviewer]:
    """Recommends reviewer roles from the subsystems this PR actually touches.

    Every recommendation traces back to specific matched file paths (the same
    evidence already computed for the category breakdown), so this is a
    GitHub-native, evidence-backed feature rather than a guess -- it reuses
    the deterministic category classification instead of inventing new signal.
    `required=True` marks roles whose sign-off should block merge (auth,
    secrets, data layer); everything else is a recommendation.
    """
    reviewers: list[SuggestedReviewer] = []
    seen_roles: dict[str, SuggestedReviewer] = {}

    for category in categories:
        if not category.evidence:
            continue
        mapping = _CATEGORY_TO_ROLE.get(category.category)
        if mapping is None:
            continue
        role, required = mapping
        matched_paths = sorted({e.file_path for e in category.evidence})
        if role in seen_roles:
            existing = seen_roles[role]
            merged_paths = sorted(set(existing.matched_paths) | set(matched_paths))
            existing.matched_paths = merged_paths
            existing.required = existing.required or required
            existing.reason = _reason_for(existing.matched_paths, existing.required, role)
        else:
            reviewer = SuggestedReviewer(
                role=role,
                reason=_reason_for(matched_paths, required, role),
                matched_paths=matched_paths,
                required=required,
            )
            seen_roles[role] = reviewer
            reviewers.append(reviewer)

    # Frontend isn't part of the fixed backend-oriented category taxonomy, so it's
    # detected directly from file paths/extensions rather than via categories.py.
    frontend_paths = sorted({f.filename for f in pr.files if _FRONTEND_RE.search(f.filename)})
    if frontend_paths:
        reviewers.append(
            SuggestedReviewer(
                role="Frontend Reviewer",
                reason=_reason_for(frontend_paths, False, "Frontend Reviewer"),
                matched_paths=frontend_paths,
                required=False,
            )
        )

    # Required reviewers first, then by number of matched files (more evidence
    # first), for a stable and useful ordering in the UI.
    reviewers.sort(key=lambda r: (not r.required, -len(r.matched_paths), r.role))
    return reviewers


def _reason_for(matched_paths: list[str], required: bool, role: str) -> str:
    shown = matched_paths[:3]
    remainder = len(matched_paths) - len(shown)
    files_desc = ", ".join(shown) + (f" (+{remainder} more)" if remainder > 0 else "")
    qualifier = "Required sign-off" if required else "Recommended"
    return f"{qualifier} -- changes touch: {files_desc}"
