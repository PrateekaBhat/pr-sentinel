from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .models import AnalyzeResponse, ChangedFile, FileRisk, RiskLevel


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _risk_label(level: RiskLevel | str) -> str:
    return level.value if isinstance(level, RiskLevel) else str(level)


def _badge(decision: str, readiness: int | None) -> str:
    if decision == "BLOCK" or (readiness is not None and readiness < 55):
        return "DO NOT MERGE"
    if decision == "ALLOW" and (readiness is None or readiness >= 80):
        return "READY"
    return "REVIEW REQUIRED BEFORE MERGE"


def _relative_path(response: AnalyzeResponse, path: str) -> str:
    prefix = f"{response.pr.repo}/{response.pr.repo}/"
    return path[len(prefix):] if path.startswith(prefix) else path


def _has_trigger(response: AnalyzeResponse, *keys: str) -> bool:
    return any(item.key in keys and item.triggered for item in response.heuristics.factors)


def _format_effort(minutes: int) -> str:
    if minutes < 60:
        return f"~{minutes} minutes"
    if minutes == 60:
        return "~1 hour"
    hours, remainder = divmod(minutes, 60)
    if remainder:
        return f"~{hours} hour{'s' if hours > 1 else ''} {remainder} minutes"
    return f"~{hours} hour{'s' if hours > 1 else ''}"


def _drivers(response: AnalyzeResponse) -> list[tuple[str, bool]]:
    metrics = response.report.engineering_metrics
    paths = [file.filename.lower() for file in response.pr.files]
    api_evidence = any(
        any(marker in path for marker in ("/api/", "api/", "routes/", "openapi", "swagger", "response_model"))
        for path in paths
    )
    return [
        ("Security-sensitive files changed", any(any(word in path for word in ("auth", "secret", "credential", "token")) for path in paths)),
        ("Infrastructure changed", bool(metrics and metrics.workflow_files_changed) or any(marker in path for path in paths for marker in ("workflow", "actions/", "terraform", "k8s/", "kubernetes/", "helm/", "dockerfile", "docker-compose"))),
        ("API contracts changed", bool(metrics and metrics.public_apis_modified) and api_evidence),
        ("Tests updated", bool(metrics and metrics.test_files_touched)),
        ("Large implementation diff", _has_trigger(response, "large_diff", "medium_diff")),
    ]


def _primary_concern(response: AnalyzeResponse) -> str:
    if _has_trigger(response, "no_tests"):
        return "Implementation changed without corresponding test updates."
    factor = next((item.reason for item in response.heuristics.factors if item.triggered), None)
    return factor or "Review the evidence-backed findings before merging."


def _actions(response: AnalyzeResponse) -> list[str]:
    paths = [file.filename.lower() for file in response.pr.files]
    actions: list[str] = []
    if _has_trigger(response, "no_tests"):
        actions.append("Add regression tests for the changed implementation paths.")
    if any("report" in path or "render" in path for path in paths):
        actions.append("Validate generated Markdown on a representative pull request.")
    if any("workflow" in path or ".github/" in path for path in paths):
        actions.append("Dry-run the modified GitHub Actions workflow on a sample pull request.")
    return actions[:3]


# ---------------------------------------------------------------------------
# File classification and review queue (single source of truth for effort)
# ---------------------------------------------------------------------------

_CATEGORY_RANK = {"implementation": 0, "api": 1, "database": 2, "infrastructure": 3, "documentation": 4}
_SEVERITY_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _file_category(filename: str) -> str:
    lower = filename.lower()
    if any(marker in lower for marker in (".github/workflows", ".github/actions", "workflow", "terraform", "k8s/", "kubernetes/", "helm/", "dockerfile", "docker-compose")):
        return "infrastructure"
    if any(marker in lower for marker in ("migration", "alembic", "schema.sql", "database/")):
        return "database"
    if any(marker in lower for marker in ("/api/", "routes/", "openapi", "swagger", "graphql", "response_model")):
        return "api"
    if lower.endswith((".md", ".rst", ".txt")) or "docs/" in lower:
        return "documentation"
    return "implementation"


def _queue_severity(response: AnalyzeResponse, filename: str, category: str) -> str:
    lower = filename.lower()
    if category in {"infrastructure", "documentation"}:
        return "LOW"
    if category == "api":
        return "MEDIUM"
    if category == "database":
        return "MEDIUM"
    is_core = any(marker in lower for marker in ("report", "render", "backend/", "engine/")) or lower.endswith(".py")
    if _has_trigger(response, "no_tests") and is_core:
        return "HIGH"
    if any(marker in lower for marker in ("report", "render")):
        return "HIGH"
    if lower.endswith((".tsx", ".jsx", ".vue", ".svelte")):
        return "MEDIUM"
    return "MEDIUM"


def _file_review_minutes(response: AnalyzeResponse, changed: ChangedFile | None, is_renderer: bool) -> int:
    changes = changed.changes if changed else 0
    minutes = max(5, round(changes / 35 / 5) * 5)
    if is_renderer:
        minutes += 5
    if _has_trigger(response, "no_tests") and changed and _file_category(changed.filename) == "implementation":
        minutes += 5
    return minutes


def _file_risk_score(response: AnalyzeResponse, filename: str, changes: int, is_renderer: bool) -> int:
    total = max(1, response.pr.additions + response.pr.deletions)
    score = 35 + round((changes / total) * 15)
    if is_renderer:
        score += 7
    if _has_trigger(response, "no_tests"):
        score += 5
    return min(95, score)


@dataclass
class ReviewQueueItem:
    filename: str
    risk: str
    severity: str
    minutes: int
    risk_score: int
    category: str
    loc_label: str
    why_reviewed: list[str]
    primary_risk: str
    reviewer_action: str


def _candidate_files(response: AnalyzeResponse) -> list[tuple[str, str, str]]:
    """Return (filename, risk, reason) tuples for queue construction."""
    assessed = [
        item for item in response.ai.file_risks
        if item.filename and not item.filename.startswith("/path/to/")
    ]
    if assessed:
        return [(item.filename, _risk_label(item.risk), item.reason) for item in assessed]
    return [
        (file.filename, _risk_label(response.ai.overall_risk), "Changed implementation file.")
        for file in sorted(response.pr.files, key=lambda item: item.changes, reverse=True)
    ]


def build_review_queue(response: AnalyzeResponse) -> list[ReviewQueueItem]:
    """Build the unified review queue — single source of truth for effort estimates."""
    pr = response.pr
    items: list[ReviewQueueItem] = []
    seen: set[str] = set()

    for filename, risk, reason in _candidate_files(response):
        rel = _relative_path(response, filename)
        if rel in seen:
            continue
        seen.add(rel)

        changed = next(
            (file for file in pr.files if _relative_path(response, file.filename) == rel),
            None,
        )
        category = _file_category(rel)
        severity = _queue_severity(response, rel, category)
        is_renderer = any(marker in rel.lower() for marker in ("report", "render"))
        loc = f"{changed.changes} LOC modified" if changed else "Changed file"
        minutes = _file_review_minutes(response, changed, is_renderer)
        risk_score = _file_risk_score(response, rel, changed.changes if changed else 0, is_renderer)

        why = [loc]
        if is_renderer:
            why.append("Core report generation logic.")
        elif category == "infrastructure":
            why.append("CI/CD or deployment configuration changed.")
        elif category == "documentation":
            why.append("Documentation-only change.")
        else:
            why.append("Changed implementation behavior.")
        if _has_trigger(response, "no_tests") and category == "implementation":
            why.append("No regression tests updated.")

        if is_renderer:
            impact = "Incorrect deployment recommendations shown to reviewers."
            action = "Compare rendered output with the previous version."
        elif category == "infrastructure":
            impact = "Pipeline or deployment regressions may block releases."
            action = "Dry-run the workflow and verify step ordering."
        elif rel.lower().endswith((".tsx", ".jsx")):
            impact = "Reviewer-facing status and evidence may render incorrectly."
            action = "Verify the report layout with a representative pull request."
        else:
            impact = "A regression in the changed behavior."
            action = "Review the changed lines and validate behavior."

        items.append(
            ReviewQueueItem(
                filename=rel,
                risk=risk,
                severity=severity,
                minutes=minutes,
                risk_score=risk_score,
                category=category,
                loc_label=loc,
                why_reviewed=why,
                primary_risk=impact,
                reviewer_action=action,
            )
        )

    items.sort(
        key=lambda item: (
            _SEVERITY_RANK[item.severity],
            _CATEGORY_RANK.get(item.category, 99),
            -next((file.changes for file in pr.files if _relative_path(response, file.filename) == item.filename), 0),
        )
    )
    return items[:5]


def _total_review_minutes(queue: list[ReviewQueueItem]) -> int:
    return sum(item.minutes for item in queue) if queue else 0


def _analysis_scope(response: AnalyzeResponse) -> dict[str, int]:
    findings = response.ai.agent_findings
    if findings:
        executed = sum(1 for item in findings if item.applicable)
        skipped = sum(1 for item in findings if not item.applicable)
    else:
        executed = sum(
            1 for item in response.report.agent_decisions
            if not item.decision.startswith("Skipped")
        )
        skipped = sum(
            1 for item in response.report.agent_decisions
            if item.decision.startswith("Skipped")
        )

    docs_matched = len(response.rag.retrieved) if response.rag.scanned else 0
    return {
        "files_analyzed": response.pr.changed_files_count,
        "files_total": response.pr.changed_files_count,
        "docs_matched": docs_matched,
        "agents_executed": executed,
        "agents_skipped": skipped,
    }


def _report_evidence_quality(response: AnalyzeResponse) -> tuple[str, list[tuple[bool, str]]]:
    """Measure how reliable this report is — not review findings."""
    checks: list[tuple[bool, str]] = [
        (True, "Deterministic analysis"),
        (response.rag.scanned and bool(response.rag.retrieved), "Repository context"),
        (True, "Changed files classified"),
        (True, "Git diff"),
        (False, "Runtime telemetry"),
    ]
    available = sum(1 for ok, _ in checks if ok)
    level = "High" if available >= 4 else "Medium" if available >= 3 else "Low"
    return level, checks


def _why_not_block(response: AnalyzeResponse) -> list[str]:
    if response.report.decision != "ALLOW":
        return []

    reasons: list[str] = []
    driver_map = dict(_drivers(response))
    if not driver_map.get("Security-sensitive files changed"):
        reasons.append("No security changes")
    if not driver_map.get("Infrastructure changed"):
        reasons.append("No infrastructure risk")
    if not driver_map.get("API contracts changed"):
        reasons.append("No API contract changes")
    if response.ai.overall_risk != RiskLevel.HIGH:
        reasons.append("No high-severity findings detected")
    if _has_trigger(response, "no_tests"):
        reasons.append("Only missing regression coverage")
    return reasons


# ---------------------------------------------------------------------------
# Template-driven report sections
# ---------------------------------------------------------------------------

@dataclass
class ReportSection:
    name: str
    render: Callable[[AnalyzeResponse, dict], list[str]]
    visible: Callable[[AnalyzeResponse, dict], bool] = field(default=lambda _r, _c: True)


def _render_header(response: AnalyzeResponse, ctx: dict) -> list[str]:
    pr = response.pr
    return [
        "# PR Sentinel",
        "",
        f"`{pr.owner}/{pr.repo}#{pr.number}` - {pr.title}",
        "",
    ]


def _render_decision(response: AnalyzeResponse, ctx: dict) -> list[str]:
    report = response.report
    readiness = report.production_readiness
    readiness_score = readiness.score if readiness else "n/a"
    strategy = report.deployment_recommendation.strategy if report.deployment_recommendation else report.deployment_strategy
    queue: list[ReviewQueueItem] = ctx["review_queue"]
    total_minutes = ctx["total_minutes"]
    effort_label = _format_effort(total_minutes) if queue else report.review_effort_label

    lines = [
        f"## Release Decision: {ctx['badge']}",
        "",
        f"- **Decision:** {report.decision} | **Risk:** {_risk_label(response.ai.overall_risk)} | **Merge readiness:** {readiness_score}/100 | **Deployment:** {strategy}",
        f"- **Estimated review effort:** {effort_label} (see Review Queue for breakdown)",
        f"- **Main review concern:** {_primary_concern(response)}",
        "- **Why this decision:** Risk is calculated from deterministic rules; AI summarizes evidence and recommends rollout.",
    ]
    return lines


def _render_why_not_block(response: AnalyzeResponse, ctx: dict) -> list[str]:
    reasons = ctx["why_not_block"]
    if not reasons:
        return []
    lines = ["", "### Why not BLOCK?", ""]
    for reason in reasons:
        lines.append(f"- ✓ {reason}")
    return lines


def _render_scorecard(response: AnalyzeResponse, ctx: dict) -> list[str]:
    lines = ["", "## Decision Scorecard", "", "| Category | Result |", "|---|---|"]
    status_words = {
        "Security-sensitive files changed": ("None", "OK"),
        "API contracts changed": ("Changed", "WARN"),
        "Tests updated": ("Updated", "OK"),
        "Infrastructure changed": ("Changed", "WARN"),
        "Large implementation diff": ("Large", "WARN"),
    }
    for label, value in _drivers(response):
        positive, _warning = status_words[label]
        if label == "Tests updated" and not value:
            status = "❌ No test updates"
        elif label == "Tests updated":
            status = "✅ Updated"
        elif value:
            status = "⚠ Large" if label == "Large implementation diff" else "⚠ Changed"
        else:
            status = f"✅ {positive if label == 'Security-sensitive files changed' else 'Unchanged'}"
        category = {
            "Security-sensitive files changed": "Security",
            "Infrastructure changed": "Platform",
            "API contracts changed": "API",
            "Tests updated": "Tests",
            "Large implementation diff": "Complexity",
        }[label]
        lines.append(f"| {category} | {status} |")
    return lines


def _render_checklist(response: AnalyzeResponse, ctx: dict) -> list[str]:
    report = response.report
    strategy = report.deployment_recommendation.strategy if report.deployment_recommendation else report.deployment_strategy
    actions = _actions(response)
    lines = ["", "## Merge Checklist", ""]
    if actions:
        lines.extend(f"- [ ] {action}" for action in actions)
    lines.extend([
        "- [ ] High-risk files reviewed.",
        f"- [ ] Ready for {strategy} deployment.",
    ])
    return lines


def _render_evidence_quality(response: AnalyzeResponse, ctx: dict) -> list[str]:
    level, checks = ctx["evidence_quality"]
    lines = ["", "## Evidence Quality", ""]
    for ok, label in checks:
        lines.append(f"- [{'x' if ok else ' '}] {label}")
    lines.append(f"- **Overall:** {level}")
    return lines


def _render_not_impacted(response: AnalyzeResponse, ctx: dict) -> list[str]:
    safe_to_ignore = [
        label for label, value in _drivers(response)
        if not value and label in {"Security-sensitive files changed", "Infrastructure changed", "API contracts changed"}
    ]
    if not safe_to_ignore:
        return []
    labels = {
        "Security-sensitive files changed": "Authentication, secrets",
        "Infrastructure changed": "Infrastructure",
        "API contracts changed": "API contracts",
    }
    lines = ["", "## No Review Needed", ""]
    lines.extend(f"- [x] {labels[item]}" for item in safe_to_ignore)
    return lines


def _render_review_queue(response: AnalyzeResponse, ctx: dict) -> list[str]:
    queue: list[ReviewQueueItem] = ctx["review_queue"]
    if not queue:
        return ["", "## Review Queue", "", "- No files require prioritized review."]
    total = ctx["total_minutes"]
    pr = response.pr
    lines = ["", "## Review Queue", ""]
    for index, item in enumerate(queue, start=1):
        lines.extend([
            f"### Priority {index} — **{item.severity}**: [`{item.filename}`]({pr.url}/files)",
            "",
            f"**{_risk_label(item.risk)} ({item.risk_score})**",
            "- **Why reviewed:**",
            *(f"  - {reason}" for reason in item.why_reviewed),
            f"- **Primary risk:** {item.primary_risk}",
            f"- **Reviewer action:** {item.reviewer_action}",
            f"- **Estimated review:** {item.minutes} minutes",
            "",
        ])
    lines.append(f"**Total review effort:** {_format_effort(total)}")
    return lines


def _render_suggested_expertise(response: AnalyzeResponse, ctx: dict) -> list[str]:
    """Domain recommendations without separate time estimates — effort lives in the queue."""
    paths = [file.filename.lower() for file in response.pr.files]
    reviewers: list[tuple[str, str]] = []
    if any(path.endswith(".py") or "backend/" in path for path in paths):
        reviewers.append(("Backend", "Verify rendered Markdown and decision-card output."))
    if _has_trigger(response, "no_tests"):
        reviewers.append(("QA", "Add or confirm regression coverage for the changed rendering paths."))
    if any(path.endswith((".tsx", ".jsx")) for path in paths):
        reviewers.append(("Frontend", "Verify decision-card and report presentation behavior."))
    metrics = response.report.engineering_metrics
    if bool(metrics and metrics.workflow_files_changed) or any("workflow" in path or ".github/" in path for path in paths):
        reviewers.append(("Platform", "Verify the updated workflow against a sample PR."))
    if dict(_drivers(response)).get("API contracts changed"):
        reviewers.append(("API", "Verify the detected public contract change is compatible."))

    if not reviewers:
        return []
    lines = ["", "## Suggested Expertise", "", "| Review domain | Focus |", "|---|---|"]
    lines.extend(f"| {role} | {task} |" for role, task in reviewers)
    return lines


def _render_risk_breakdown(response: AnalyzeResponse, ctx: dict) -> list[str]:
    report = response.report
    readiness = report.production_readiness
    readiness_score = readiness.score if readiness else "n/a"
    lines = [
        "",
        f"## Why this PR scored {report.risk_score}/100",
        "",
        "| Contributor | Points |",
        "|---|---:|",
    ]
    for rule in report.score_math:
        if rule.points:
            lines.append(f"| {rule.factor} | +{rule.points} |")
    lines.append(f"| **Final risk score** | **{report.risk_score} / 100** |")
    lines.append(
        f"\nMerge readiness is **{readiness_score}/100** because it combines risk, evidence quality, testing, and documentation completeness."
    )
    return lines


def _render_analysis_scope(response: AnalyzeResponse, ctx: dict) -> list[str]:
    scope = ctx["analysis_scope"]
    lines = [
        "",
        "### Analysis Scope",
        "",
        f"- **Files analyzed:** {scope['files_analyzed']} / {scope['files_total']}",
        f"- **Repository docs matched:** {scope['docs_matched']}",
        f"- **Agents executed:** {scope['agents_executed']}",
        f"- **Agents skipped:** {scope['agents_skipped']}",
    ]
    return lines


def _render_repository_evidence(response: AnalyzeResponse, ctx: dict) -> list[str]:
    rag = response.rag
    docs = list(dict.fromkeys((rag.indexed_doc_paths or []) + [chunk.path for chunk in rag.retrieved]))
    level, _ = ctx["evidence_quality"]
    lines = ["", "### Repository Evidence", ""]
    if docs:
        if any("readme" in path.lower() for path in docs):
            lines.append("- **Consulted:** `README.md`")
            lines.append("- **Architecture matched:** [x] Report Generation; [x] Multi-agent Pipeline.")
        else:
            lines.append("- **Consulted:** " + ", ".join(f"`{path}`" for path in docs[:3]))
        lines.append(f"- **Repository coverage:** {level}.")
    else:
        lines.append("- Repository documentation was not available; findings rely on deterministic PR evidence.")
    return lines


def _render_analysis_performed(response: AnalyzeResponse, ctx: dict) -> list[str]:
    scope = ctx["analysis_scope"]
    report = response.report
    lines = [
        "",
        "### Analysis Performed",
        "",
        "- [x] Rule Engine",
        f"- [{'x' if ctx['has_docs'] else ' '}] Repository Retrieval",
        f"- [{'x' if scope['agents_executed'] else ' '}] Specialist Agents",
        f"- [{'x' if response.ai_enabled else ' '}] Coordinator Synthesis",
    ]
    return lines


def _render_evidence_details(response: AnalyzeResponse, ctx: dict) -> list[str]:
    if not ctx["has_docs"] and not response.rag.scanned:
        return []
    lines = ["", "<details>", "<summary><strong>Evidence</strong></summary>"]
    lines.extend(_render_repository_evidence(response, ctx))
    lines.extend(["", "</details>"])
    return lines


def _render_diagnostics_details(response: AnalyzeResponse, ctx: dict) -> list[str]:
    lines = ["", "<details>", "<summary><strong>Diagnostics</strong></summary>"]
    lines.extend(_render_analysis_performed(response, ctx))
    lines.extend(_render_analysis_scope(response, ctx))
    lines.extend(["", "</details>"])
    return lines


REPORT_SECTIONS: list[ReportSection] = [
    ReportSection("header", _render_header),
    ReportSection("decision", _render_decision),
    ReportSection("why_not_block", _render_why_not_block, visible=lambda r, c: bool(c["why_not_block"])),
    ReportSection("scorecard", _render_scorecard),
    ReportSection("checklist", _render_checklist),
    ReportSection("evidence_quality", _render_evidence_quality),
    ReportSection("not_impacted", _render_not_impacted, visible=lambda r, c: bool(c.get("safe_to_ignore"))),
    ReportSection("review_queue", _render_review_queue),
    ReportSection("suggested_expertise", _render_suggested_expertise, visible=lambda r, c: bool(c.get("has_reviewers"))),
    ReportSection("risk_breakdown", _render_risk_breakdown),
    ReportSection("evidence_details", _render_evidence_details, visible=lambda r, c: c["has_docs"]),
    ReportSection("diagnostics_details", _render_diagnostics_details),
]


def _build_context(response: AnalyzeResponse) -> dict:
    report = response.report
    readiness = report.production_readiness
    review_queue = build_review_queue(response)
    total_minutes = _total_review_minutes(review_queue)
    evidence_quality = _report_evidence_quality(response)
    docs = response.rag.scanned and bool(response.rag.retrieved)
    safe_to_ignore = [
        label for label, value in _drivers(response)
        if not value and label in {"Security-sensitive files changed", "Infrastructure changed", "API contracts changed"}
    ]

    paths = [file.filename.lower() for file in response.pr.files]
    has_reviewers = (
        any(path.endswith(".py") or "backend/" in path for path in paths)
        or _has_trigger(response, "no_tests")
        or any(path.endswith((".tsx", ".jsx")) for path in paths)
        or dict(_drivers(response)).get("API contracts changed")
    )

    return {
        "badge": _badge(report.decision, readiness.score if readiness else None),
        "review_queue": review_queue,
        "total_minutes": total_minutes,
        "evidence_quality": evidence_quality,
        "analysis_scope": _analysis_scope(response),
        "why_not_block": _why_not_block(response),
        "has_docs": docs,
        "safe_to_ignore": safe_to_ignore,
        "has_reviewers": has_reviewers,
    }


def render_markdown(response: AnalyzeResponse) -> str:
    """Render a merge-decision report from modular, conditionally-visible sections."""
    ctx = _build_context(response)
    lines: list[str] = []
    for section in REPORT_SECTIONS:
        if section.visible(response, ctx):
            lines.extend(section.render(response, ctx))
    return "\n".join(lines)


def render_comment(response: AnalyzeResponse) -> str:
    return render_markdown(response)


def render_console(response: AnalyzeResponse) -> str:
    report, ai = response.report, response.ai
    readiness = report.production_readiness.score if report.production_readiness else "n/a"
    return f"PR Sentinel | {report.decision} | {_risk_label(ai.overall_risk)} risk | readiness {readiness}/100"
