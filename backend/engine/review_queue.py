"""Prioritized review queue — files ranked by review value, not raw diff size."""

from __future__ import annotations

import re

from . import agent_routing
from .categories import classify_files
from .models import ChangedFile, HeuristicResult, PullRequestData, ReviewQueueItem, RiskLevel

_TEST_RE = re.compile(r"(^|/)(tests?|__tests__|spec)(/|\.)|\.(test|spec)\.", re.I)
_DOC_RE = re.compile(r"\.(md|mdx|rst)$|(^|/)docs?/", re.I)

_ROLE_LABELS = {
    "security": "Security-sensitive",
    "database": "Database / migration",
    "api": "API / application logic",
    "performance": "Performance-critical",
    "tests": "Test coverage",
}


def _file_role(filename: str, buckets: dict[str, list[ChangedFile]]) -> str:
    for domain, pattern_files in [
        ("security", agent_routing.files_for_domain([ChangedFile(filename=filename, status="modified", additions=0, deletions=0, changes=0)], "security")),
        ("database", agent_routing.files_for_domain([ChangedFile(filename=filename, status="modified", additions=0, deletions=0, changes=0)], "database")),
    ]:
        if pattern_files:
            return _ROLE_LABELS[domain]

    for category, files in buckets.items():
        if any(f.filename == filename for f in files):
            if category in ("Authentication", "Secrets"):
                return "Security-sensitive"
            if category == "Data Layer":
                return "Database / migration"
            if category == "API":
                return "API / application logic"
            if category == "Infrastructure":
                return "Infrastructure / deployment"
            if category == "Application/Core Logic":
                return "Core backend logic"
            if category == "Tests":
                return "Test coverage"
            if category == "Documentation":
                return "Documentation"

    if _TEST_RE.search(filename):
        return "Test coverage"
    if _DOC_RE.search(filename):
        return "Documentation"
    if re.search(r"\.(tsx|jsx|css|vue)$", filename, re.I):
        return "Frontend / UI"
    return "Supporting production code"


def _priority_for(
    filename: str,
    f: ChangedFile,
    heuristics: HeuristicResult,
    buckets: dict[str, list[ChangedFile]],
) -> str:
    """P1–P4 priority based on domain + risk signals, not raw line count."""
    if _TEST_RE.search(filename) or _DOC_RE.search(filename):
        return "P4"

    security_files = {x.filename for x in agent_routing.files_for_domain([f], "security")}
    db_files = {x.filename for x in agent_routing.files_for_domain([f], "database")}

    if filename in security_files or any(
        c in ("Authentication", "Secrets") for c, files in buckets.items() if any(x.filename == filename for x in files)
    ):
        return "P1"
    if filename in db_files or heuristics.migration_touched and "migration" in filename.lower():
        return "P1"

    for category in ("Application/Core Logic", "API"):
        cat_files = buckets.get(category, [])
        if any(x.filename == filename for x in cat_files):
            return "P2"

    if re.search(r"\.(tsx|jsx|css|vue)$", filename, re.I):
        return "P3"

    return "P3"


def _why_it_matters(filename: str, role: str, heuristics: HeuristicResult) -> str:
    if "Security" in role:
        return "Authentication or security-sensitive path; regression could affect access control."
    if "Database" in role or "migration" in role.lower():
        return "Persistence-layer change; verify reversibility and staging validation."
    if "API" in role:
        return "Public or internal API surface; check backward compatibility."
    if role == "Test coverage":
        return "Test changes validate production behavior — review assertions, not just line count."
    if role == "Documentation":
        return "Docs-only; verify accuracy and link integrity."
    if heuristics.tests_deleted and _TEST_RE.search(filename):
        return "Test file removed — confirm intentional retirement."
    return "Production code change; review logic correctness and edge cases."


def _regression_hint(role: str) -> str:
    hints = {
        "Security-sensitive": "Auth bypass, session invalidation, privilege escalation",
        "Database / migration": "Schema drift, failed migration, data loss on rollback",
        "API / application logic": "Breaking API contracts, incorrect business logic",
        "Core backend logic": "Silent data corruption, incorrect orchestration",
        "Infrastructure / deployment": "Broken deploy pipeline, misconfigured environments",
        "Frontend / UI": "UI regressions, broken client flows",
        "Test coverage": "False confidence from weakened assertions",
        "Documentation": "Stale docs misleading operators",
    }
    return hints.get(role, "Unexpected behavior in affected code paths")


def _validation_hint(role: str) -> str:
    hints = {
        "Security-sensitive": "Run auth integration tests; verify token/session invalidation",
        "Database / migration": "Apply migration on staging snapshot; verify rollback script",
        "API / application logic": "Exercise affected endpoints; check contract tests",
        "Core backend logic": "Run unit + integration tests for changed modules",
        "Infrastructure / deployment": "Dry-run pipeline / IaC plan in lower environment",
        "Frontend / UI": "Manual smoke test of affected UI flows",
        "Test coverage": "Confirm tests fail when production logic is broken",
        "Documentation": "Run link checker on docs build",
    }
    return hints.get(role, "Run targeted tests for this file's module")


def _estimate_minutes(priority: str, changes: int) -> int:
    base = {"P1": 20, "P2": 15, "P3": 10, "P4": 5}.get(priority, 10)
    if changes > 500:
        return base + 15
    if changes > 200:
        return base + 10
    if changes > 80:
        return base + 5
    return base


def build_review_queue(
    pr: PullRequestData,
    heuristics: HeuristicResult,
    *,
    limit: int = 5,
) -> list[ReviewQueueItem]:
    """Build a prioritized review queue; tests/docs deprioritized despite large diffs."""
    buckets = classify_files(pr.files)
    items: list[ReviewQueueItem] = []

    for f in pr.files:
        role = _file_role(f.filename, buckets)
        priority = _priority_for(f.filename, f, heuristics, buckets)
        items.append(
            ReviewQueueItem(
                priority=priority,
                filename=f.filename,
                role=role,
                why_it_matters=_why_it_matters(f.filename, role, heuristics),
                potential_regression=_regression_hint(role),
                suggested_validation=_validation_hint(role),
                estimated_minutes=_estimate_minutes(priority, f.changes),
            )
        )

    priority_order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    items.sort(key=lambda i: (priority_order.get(i.priority, 9), -pr.files[[x.filename for x in pr.files].index(i.filename)].changes if i.filename in [x.filename for x in pr.files] else 0))

    # Re-sort by priority then change size
    file_changes = {f.filename: f.changes for f in pr.files}
    items.sort(key=lambda i: (priority_order.get(i.priority, 9), -file_changes.get(i.filename, 0)))

    return items[:limit]
