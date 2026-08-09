"""Deterministic review-complexity scoring — separate from release risk.

A large documentation refactor can be hard to review (HIGH complexity) but
safe to deploy (LOW release risk). This module captures that distinction.
"""

from __future__ import annotations

import re

from .categories import classify_files
from .models import ChangedFile, HeuristicResult, PullRequestData, ReviewComplexityResult, RiskLevel

_TEST_RE = re.compile(r"(^|/)(tests?|__tests__|spec)(/|\.)|\.(test|spec)\.", re.I)
_FRONTEND_RE = re.compile(r"(^|/)(frontend|client|ui|web)(/|\.)|\.(tsx|jsx|vue)$", re.I)
_BACKEND_RE = re.compile(r"(^|/)(backend|server|api|engine|src)(/|\.)|\.(py|go|java|rb)$", re.I)
_INFRA_RE = re.compile(r"(^|/)(terraform|infra|deploy|docker|k8s|\.github/workflows)(/|\.)", re.I)
_DEPS_RE = re.compile(
    r"(^|/)(package(-lock)?\.json|requirements.*\.txt|pyproject\.toml|go\.(mod|sum)|poetry\.lock)$",
    re.I,
)


def _largest_file_concentration(files: list[ChangedFile]) -> tuple[str, int]:
    if not files:
        return "n/a", 0
    total = sum(f.changes for f in files) or 1
    largest = max(files, key=lambda f: f.changes)
    pct = round((largest.changes / total) * 100)
    return largest.filename, pct


def _cross_layer(files: list[ChangedFile]) -> bool:
    has_frontend = any(_FRONTEND_RE.search(f.filename) for f in files)
    has_backend = any(_BACKEND_RE.search(f.filename) for f in files)
    return has_frontend and has_backend


def calculate_review_complexity(
    pr: PullRequestData,
    heuristics: HeuristicResult,
) -> ReviewComplexityResult:
    """Score how much human review effort this PR requires — not how dangerous it is."""
    files = pr.files
    total_lines = pr.additions + pr.deletions
    file_count = pr.changed_files_count or len(files)
    buckets = classify_files(files)
    subsystem_count = sum(1 for c in buckets.values() if c)

    score = 0
    drivers: list[str] = []

    # Changed LOC
    if total_lines >= 2000:
        score += 35
        drivers.append(f"{total_lines:,} lines changed")
    elif total_lines >= 800:
        score += 25
        drivers.append(f"{total_lines:,} lines changed")
    elif total_lines >= 300:
        score += 15
        drivers.append(f"{total_lines:,} lines changed")
    elif total_lines >= 100:
        score += 8

    # File count
    if file_count >= 15:
        score += 20
        drivers.append(f"{file_count} files changed")
    elif file_count >= 8:
        score += 15
        drivers.append(f"{file_count} files changed")
    elif file_count >= 4:
        score += 8

    # Subsystem spread
    if subsystem_count >= 5:
        score += 15
        drivers.append(f"{subsystem_count} subsystems touched")
    elif subsystem_count >= 3:
        score += 10
        drivers.append(f"{subsystem_count} subsystems touched")

    # Cross-layer
    if _cross_layer(files):
        score += 12
        drivers.append("Backend + frontend touched")

    # Hotspot concentration
    largest_file, concentration = _largest_file_concentration(files)
    if concentration >= 60 and total_lines >= 200:
        score += 10
        drivers.append(f"Largest file contains {concentration}% of diff ({largest_file})")

    # Infrastructure / schema (review burden, not release risk)
    if any(_INFRA_RE.search(f.filename) for f in files):
        score += 8
        drivers.append("Infrastructure or workflow files changed")

    if heuristics.migration_touched:
        score += 10
        drivers.append("Database migration files present")

    # Dependency churn
    dep_files = sum(1 for f in files if _DEPS_RE.search(f.filename))
    if dep_files >= 2:
        score += 10
        drivers.append(f"{dep_files} dependency manifest(s) updated")
    elif dep_files == 1:
        score += 5

    # Test/code ratio — many test changes add review surface but lower production risk
    test_files = [f for f in files if _TEST_RE.search(f.filename)]
    code_files = [f for f in files if not _TEST_RE.search(f.filename)]
    if code_files and len(test_files) >= len(code_files):
        score += 5
        drivers.append("Substantial test file updates alongside code")

    score = min(100, score)

    if score >= 50:
        level = RiskLevel.HIGH
    elif score >= 25:
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.LOW

    if not drivers and level == RiskLevel.LOW:
        drivers.append("Small, focused change surface")

    return ReviewComplexityResult(score=score, level=level, drivers=drivers)
