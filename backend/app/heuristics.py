from __future__ import annotations

import re

from .models import HeuristicFactor, HeuristicResult, PullRequestData

# Each rule: (key, label, weight, path/content pattern)
PATH_RULES: list[tuple[str, str, int, re.Pattern]] = [
    ("auth", "Authentication logic touched", 40, re.compile(r"(^|/)(auth|authn|authz|login|session)(/|\.)", re.I)),
    ("payment", "Payment / billing logic touched", 45, re.compile(r"(^|/)(payment|billing|checkout|stripe|invoice)(/|\.)", re.I)),
    ("config", "Configuration files changed", 30, re.compile(r"(^|/)(config|settings|\.env|helm|k8s|kubernetes)(/|\.)", re.I)),
    ("infra", "Infrastructure / deployment files changed", 30, re.compile(r"(^|/)(terraform|infra|deploy|docker|ci|\.github/workflows)(/|\.)", re.I)),
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
        score += 15
        factors.append(
            HeuristicFactor(
                key="no_tests",
                label="No test files touched",
                triggered=True,
                weight=15,
                reason="This PR changes code but doesn't add or modify any tests.",
            )
        )

    # Large diffs carry more residual risk regardless of category
    total_changes = pr.additions + pr.deletions
    if total_changes > 800:
        score += 20
        factors.append(
            HeuristicFactor(
                key="large_diff",
                label="Large diff (800+ line changes)",
                triggered=True,
                weight=20,
                reason=f"{total_changes} lines changed across {pr.changed_files_count} files.",
            )
        )
    elif total_changes > 300:
        score += 10
        factors.append(
            HeuristicFactor(
                key="medium_diff",
                label="Medium-sized diff (300+ line changes)",
                triggered=True,
                weight=10,
                reason=f"{total_changes} lines changed across {pr.changed_files_count} files.",
            )
        )

    score = min(score, 100)

    return HeuristicResult(
        score=score,
        factors=factors,
        tests_touched=tests_touched,
        tests_deleted=tests_deleted,
        migration_touched="migration" in matched_keys,
    )
