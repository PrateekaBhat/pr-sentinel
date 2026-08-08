from __future__ import annotations

import re

from .models import HeuristicFactor, HeuristicResult, PullRequestData, ScoreMathFactor

# Each rule: (key, label, weight, path/content pattern)
PATH_RULES: list[tuple[str, str, int, re.Pattern]] = [
    ("auth", "Authentication logic touched", 40, re.compile(r"(^|/)(auth|authn|authz|login|session)(/|\.)", re.I)),
    ("payment", "Payment / billing logic touched", 45, re.compile(r"(^|/)(payment|billing|checkout|stripe|invoice)(/|\.)", re.I)),
    ("config", "Configuration files changed", 30, re.compile(r"(^|/)(config|settings|\.env|helm|k8s|kubernetes)(/|\.)", re.I)),
    # Reduced from 30 → 20: a CI/CD workflow change is lower risk than a genuine
    # IaC or deployment change (Terraform, Kubernetes, Docker). The workflow
    # heuristic fires frequently on routine PRs and was over-inflating scores.
    ("infra", "Infrastructure / deployment files changed", 20, re.compile(r"(^|/)(terraform|infra|deploy|docker|ci|\.github/workflows)(/|\.)", re.I)),
    ("migration", "Database migration detected", 35, re.compile(r"(^|/)(migrations?|schema)(/|\.).*\.(sql|py|ts|js)$|alembic", re.I)),
    ("api_contract", "Public API contract changed", 25, re.compile(r"(^|/)(routes?|controllers?|api|graphql|schema\.graphql|openapi)(/|\.)", re.I)),
]

TEST_PATH_RE = re.compile(r"(^|/)(tests?|__tests__|spec)(/|\.)|\.(test|spec)\.", re.I)


def analyze(pr: PullRequestData) -> HeuristicResult:
    factors: list[HeuristicFactor] = []
    score = 0

    matched_keys: set[str] = set()
    for key, label, weight, pattern in PATH_RULES:
        triggered = any(pattern.search(f.filename) for f in pr.files)
        if triggered:
            score += weight
            matched_keys.add(key)
        example = next((f.filename for f in pr.files if pattern.search(f.filename)), None)
        reason = f"Matched in {example}" if example else "No matching files in this diff."
        factors.append(HeuristicFactor(key=key, label=label, triggered=triggered, weight=weight, reason=reason))

    tests_touched = any(TEST_PATH_RE.search(f.filename) for f in pr.files)
    tests_deleted = any(
        TEST_PATH_RE.search(f.filename) and f.status == "removed" for f in pr.files
    )
    if tests_deleted:
        score += 25
        factors.append(
            HeuristicFactor(
                key="tests_deleted",
                label="Test files were deleted",
                triggered=True,
                weight=25,
                reason="One or more test files were removed in this PR.",
            )
        )

    non_test_files = [f for f in pr.files if not TEST_PATH_RE.search(f.filename)]
    if non_test_files and not tests_touched:
        # Reduced from 15 → 10: missing tests is a signal worth noting, but a
        # documentation-heavy or report-generation PR should not score 15 pts
        # just because it touches no test files.
        score += 10
        factors.append(
            HeuristicFactor(
                key="no_tests",
                label="No test files touched",
                triggered=True,
                weight=10,
                reason="This PR changes code but doesn't add or modify any tests.",
            )
        )

    # Diff-size signals inform review complexity, NOT release risk.
    review_signals: list[HeuristicFactor] = []
    total_changes = pr.additions + pr.deletions
    if total_changes > 800:
        review_signals.append(
            HeuristicFactor(
                key="large_diff",
                label="Large diff (800+ line changes)",
                triggered=True,
                weight=0,
                reason=f"{total_changes} lines changed across {pr.changed_files_count} files.",
            )
        )
    elif total_changes > 300:
        review_signals.append(
            HeuristicFactor(
                key="medium_diff",
                label="Medium-sized diff (300+ line changes)",
                triggered=True,
                weight=0,
                reason=f"{total_changes} lines changed across {pr.changed_files_count} files.",
            )
        )

    score_math: list[ScoreMathFactor] = [
        ScoreMathFactor(factor="Base Risk", points=0, reason="Clean starting baseline")
    ]
    for factor in factors:
        if factor.triggered:
            score_math.append(
                ScoreMathFactor(factor=factor.label, points=factor.weight, reason=factor.reason)
            )

    score = min(score, 100)

    return HeuristicResult(
        score=score,
        factors=factors,
        score_math=score_math,
        tests_touched=tests_touched,
        tests_deleted=tests_deleted,
        migration_touched="migration" in matched_keys,
        review_signals=review_signals,
    )


def calculate_review_effort(pr: PullRequestData, heuristics: HeuristicResult) -> tuple[int, str]:
    """Deterministically estimates the time required for a thorough human code review."""
    from .review_complexity import calculate_review_complexity

    complexity = calculate_review_complexity(pr, heuristics)
    total_changes = pr.additions + pr.deletions

    # Base estimate from review complexity level
    if complexity.level.value == "HIGH":
        minutes = 120 if total_changes >= 2000 else 60
    elif complexity.level.value == "MEDIUM":
        minutes = 30 if total_changes < 600 else 60
    else:
        if total_changes < 50 and pr.changed_files_count <= 2:
            minutes = 5
        elif total_changes < 200:
            minutes = 15
        else:
            minutes = 30

    # Release-risk adjustments (review thoroughness, not decision)
    if heuristics.score >= 60:
        minutes = max(minutes, 60)
    elif heuristics.score >= 30:
        minutes = max(minutes, 30)

    if minutes < 60:
        label = f"{minutes} minutes"
    elif minutes == 60:
        label = "1 hour"
    else:
        label = f"{minutes // 60} hours {minutes % 60} minutes" if minutes % 60 else f"{minutes // 60} hours"

    return minutes, label
