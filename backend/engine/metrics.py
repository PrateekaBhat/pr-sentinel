"""Deterministic engineering metrics and the operational pre-merge checklist.

Both of these are pure functions over already-computed data (the PR's changed
files, the category breakdown, and the heuristic result) — no LLM calls. This
keeps them reproducible: the same PR always produces the same numbers and the
same checklist, which is the point of keeping static analysis and LLM
reasoning separate (see categories.py for the category classifier that feeds
this module).
"""

from __future__ import annotations

import re

from .models import (
    ChangedFile,
    ChecklistItem,
    EngineeringMetrics,
    HeuristicResult,
    ProductionReadinessScore,
    PullRequestData,
    RiskCategory,
    RiskLevel,
)

# A conservative regex for "this line looks like a new public function/route",
# used only to produce a rough count — not a substitute for real AST parsing,
# but good enough to say "5 new public functions" instead of nothing at all.
_NEW_PUBLIC_FUNC_RE = re.compile(
    r"^\+\s*(def |export function |export async function |func |public [\w<>\[\]]+ \w+\()",
)
_NEW_ROUTE_RE = re.compile(
    r"^\+.*(@(app|router)\.(get|post|put|patch|delete)|app\.(get|post|put|patch|delete)\(|Route\(|@RequestMapping)",
    re.I,
)

_CONFIG_FILE_RE = re.compile(
    r"(^|/)(\.env(\.\w+)?|config(/|\.)|settings\.(py|json|ya?ml)|application\.(ya?ml|properties))",
    re.I,
)
_WORKFLOW_FILE_RE = re.compile(
    r"(^|/)(\.github/workflows/|\.gitlab-ci|jenkinsfile|\.circleci/)",
    re.I,
)
_DOC_FILE_RE = re.compile(r"\.(md|mdx|rst)$|(^|/)docs?/", re.I)


def _count_pattern_in_patches(files: list[ChangedFile], pattern: re.Pattern) -> int:
    total = 0
    for f in files:
        if not f.patch:
            continue
        for line in f.patch.splitlines():
            if pattern.match(line):
                total += 1
    return total


def build_engineering_metrics(
    pr: PullRequestData,
    categories: list[RiskCategory],
) -> EngineeringMetrics:
    """Deterministic, reproducible counts describing the shape of the change —
    an expansion of the old 'files changed' line into what an engineer actually
    wants to know before reviewing: how much of this is API surface, config,
    pipeline, or docs, versus everything else."""
    files = pr.files

    api_category = next((c for c in categories if c.category == "API"), None)
    api_routes_changed = len(api_category.evidence_files) if api_category else 0

    config_files_changed = sum(1 for f in files if _CONFIG_FILE_RE.search(f.filename))
    workflow_files_changed = sum(1 for f in files if _WORKFLOW_FILE_RE.search(f.filename))
    doc_files_changed = sum(1 for f in files if _DOC_FILE_RE.search(f.filename))

    deps_category = next((c for c in categories if c.category == "Dependencies"), None)
    dependency_updates = len(deps_category.evidence_files) if deps_category else 0

    tests_category = next((c for c in categories if c.category == "Tests"), None)
    test_files_touched = len(tests_category.evidence_files) if tests_category else 0
    non_test_files = pr.changed_files_count - test_files_touched
    # Rough proxy: ratio of test file churn to overall churn, as a signed delta
    # rather than an absolute coverage percentage (which would require running
    # a coverage tool this module deliberately does not have access to).
    test_coverage_delta_files = test_files_touched - (1 if non_test_files > 0 and test_files_touched == 0 else 0)

    public_apis_modified = _count_pattern_in_patches(files, _NEW_PUBLIC_FUNC_RE) + _count_pattern_in_patches(
        files, _NEW_ROUTE_RE
    )

    deleted_files = sum(1 for f in files if f.status == "removed")

    largest_file = ""
    largest_file_changes = 0
    for f in files:
        if f.changes > largest_file_changes:
            largest_file_changes = f.changes
            largest_file = f.filename

    # Most impacted subsystem: the category with the most evidence items,
    # excluding Documentation/Tests which are rarely the "point" of a PR.
    ranked = sorted(
        (c for c in categories if c.category not in ("Documentation",)),
        key=lambda c: len(c.evidence),
        reverse=True,
    )
    most_impacted_subsystem = ranked[0].category if ranked and ranked[0].evidence else "None"

    doc_coverage_pct = round((doc_files_changed / pr.changed_files_count) * 100) if pr.changed_files_count else 0

    # --- Ratio metrics (Feature 2) ------------------------------------------
    # Risk density: how much risk per file touched. A PR that scores 40 across
    # 3 files is a very different signal than 40 across 60 files.
    risk_density = round(sum(c.score for c in categories) / pr.changed_files_count, 2) if pr.changed_files_count else 0.0

    critical_categories = {"Authentication", "Secrets", "Data Layer"}
    critical_files = {
        f for c in categories if c.category in critical_categories for f in c.evidence_files
    }
    critical_file_ratio = round(len(critical_files) / pr.changed_files_count, 3) if pr.changed_files_count else 0.0

    code_files = [
        f for f in files
        if not _DOC_FILE_RE.search(f.filename) and not (tests_category and f.filename in tests_category.evidence_files)
    ]
    test_ratio = round(test_files_touched / len(code_files), 3) if code_files else 0.0

    documentation_ratio = round(doc_files_changed / pr.changed_files_count, 3) if pr.changed_files_count else 0.0

    average_file_diff_size = round((pr.additions + pr.deletions) / pr.changed_files_count, 1) if pr.changed_files_count else 0.0

    total_changes = sum(f.changes for f in files) or 1
    hotspot_concentration_pct = round((largest_file_changes / total_changes) * 100) if largest_file_changes else 0

    return EngineeringMetrics(
        public_apis_modified=public_apis_modified,
        api_routes_changed=api_routes_changed,
        config_files_changed=config_files_changed,
        workflow_files_changed=workflow_files_changed,
        documentation_files_changed=doc_files_changed,
        documentation_coverage_pct=doc_coverage_pct,
        test_files_touched=test_files_touched,
        test_coverage_delta_files=test_coverage_delta_files,
        dependency_updates=dependency_updates,
        lines_added=pr.additions,
        lines_removed=pr.deletions,
        deleted_files=deleted_files,
        largest_file=largest_file or "n/a",
        largest_file_changes=largest_file_changes,
        most_impacted_subsystem=most_impacted_subsystem,
        risk_density=risk_density,
        critical_file_ratio=critical_file_ratio,
        test_ratio=test_ratio,
        dependency_churn=dependency_updates,
        documentation_ratio=documentation_ratio,
        average_file_diff_size=average_file_diff_size,
        hotspot_concentration_pct=hotspot_concentration_pct,
    )


def build_operational_checklist(
    categories: list[RiskCategory],
    heuristics: HeuristicResult,
    metrics: EngineeringMetrics,
) -> list[ChecklistItem]:
    """Turn detected risks into concrete, actionable pre-merge tasks. Every item
    traces back to a specific category or metric — nothing here is generic
    filler, so an empty-risk PR gets a short checklist and a risky one gets a
    longer, specific one."""
    items: list[ChecklistItem] = []
    by_category = {c.category: c for c in categories}

    def add(task: str, reason: str) -> None:
        items.append(ChecklistItem(task=task, reason=reason))

    # Always-on baseline.
    add("Run the full test suite", "Standard pre-merge gate for any code change.")

    if heuristics.tests_touched or (by_category.get("Tests") and by_category["Tests"].evidence):
        if metrics.test_files_touched == 0:
            add(
                "Add or restore test coverage for the changed logic",
                "No test files were touched despite non-test code changing.",
            )
    if heuristics.migration_touched or (by_category.get("Data Layer") and by_category["Data Layer"].evidence):
        add(
            "Validate the database migration against a staging copy of production data",
            "This PR touches the persistence layer; migrations are hard to safely revert.",
        )

    auth_cat = by_category.get("Authentication")
    if auth_cat and auth_cat.evidence:
        add(
            "Get an explicit review from the security/auth code-owners group",
            "This PR modifies authentication/authorization logic.",
        )

    secrets_cat = by_category.get("Secrets")
    if secrets_cat and secrets_cat.evidence:
        add(
            "Confirm no plaintext secret was committed and rotate any exposed credential",
            "This PR touches files matched as secrets/credentials.",
        )

    api_cat = by_category.get("API")
    if api_cat and api_cat.evidence:
        add(
            "Confirm API changes are backward compatible or version-bumped",
            f"{metrics.api_routes_changed} API-layer file(s) changed; existing clients may be affected.",
        )

    if metrics.workflow_files_changed:
        add(
            "Dry-run the updated CI/CD workflow on a branch before merging",
            f"{metrics.workflow_files_changed} workflow file(s) changed.",
        )

    infra_cat = by_category.get("Infrastructure")
    if infra_cat and infra_cat.evidence:
        add(
            "Review the deployment/IaC diff with an SRE and stage through a lower environment",
            "This PR modifies infrastructure/deployment configuration.",
        )

    if metrics.dependency_updates:
        add(
            "Review the changelog/CVE feed for updated dependencies",
            f"{metrics.dependency_updates} dependency manifest/lock file(s) changed.",
        )

    if metrics.config_files_changed:
        add(
            "Verify updated configuration values against each deployment environment",
            f"{metrics.config_files_changed} configuration file(s) changed.",
        )

    if heuristics.tests_deleted:
        add(
            "Confirm removed tests were intentionally retired, not accidentally deleted",
            "This PR deletes existing test files.",
        )

    add("Confirm the rollback plan for this change", "Standard release-safety gate before merge.")

    return items


def derive_production_readiness_score(
    heuristics: HeuristicResult,
    categories: list[RiskCategory],
    confidence: int,
    em: EngineeringMetrics,
) -> ProductionReadinessScore:
    """A single 0-100 score summarizing 'is this ready to ship', built entirely
    from numbers already computed elsewhere in the pipeline — deterministic and
    reproducible, not an LLM guess. Starts at 100 and subtracts points for each
    concrete readiness gap, so the explanation is just the list of deductions."""
    score = 100
    reasons: list[str] = []
    by_category = {c.category: c for c in categories}

    # Risk
    risk_penalty = min(35, heuristics.score // 3)
    if risk_penalty:
        score -= risk_penalty
        reasons.append(f"-{risk_penalty} for overall risk score ({heuristics.score}/100)")

    # Confidence
    if confidence < 70:
        conf_penalty = min(15, (70 - confidence) // 2)
        score -= conf_penalty
        reasons.append(f"-{conf_penalty} for below-target confidence ({confidence}%)")

    # Tests
    if em.test_files_touched == 0 and by_category.get("Application/Core Logic", None) and by_category["Application/Core Logic"].evidence:
        score -= 15
        reasons.append("-15 for no test files touched despite implementation changes")
    elif heuristics.tests_deleted:
        score -= 8
        reasons.append("-8 for deleted test files")

    # Deployment complexity proxy: infra/CI/DB categories touched together
    complexity_categories = [c for c in ("Infrastructure", "CI/CD", "Data Layer") if by_category.get(c) and by_category[c].evidence]
    if len(complexity_categories) >= 2:
        score -= 10
        reasons.append(f"-10 for multi-domain deployment complexity ({', '.join(complexity_categories)})")

    # Documentation
    if em.documentation_ratio == 0 and em.lines_added > 300:
        score -= 5
        reasons.append("-5 for a large change with no accompanying documentation update")

    # Secrets
    secrets_cat = by_category.get("Secrets")
    if secrets_cat and secrets_cat.evidence:
        score -= 20
        reasons.append("-20 for changes touching files matched as secrets/credentials")

    # Dependencies
    if em.dependency_updates > 3:
        score -= 5
        reasons.append(f"-5 for high dependency churn ({em.dependency_updates} manifests changed)")

    score = max(0, min(100, score))
    if score >= 80:
        label = "Ready"
    elif score >= 55:
        label = "Needs attention"
    else:
        label = "Not ready"

    return ProductionReadinessScore(score=score, label=label, deductions=reasons)
