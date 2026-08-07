from __future__ import annotations

from .models import AnalyzeResponse, RiskLevel


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


def _suggested_reviewers(response: AnalyzeResponse) -> list[tuple[str, str]]:
    paths = [file.filename.lower() for file in response.pr.files]
    metrics = response.report.engineering_metrics
    reviewers: list[tuple[str, str]] = []
    if any(path.endswith(".py") or "backend/" in path for path in paths):
        reviewers.append(("Backend", "Verify rendered Markdown and decision-card output."))
    if _has_trigger(response, "no_tests"):
        reviewers.append(("QA", "Add or confirm regression coverage for the changed rendering paths."))
    if any(path.endswith(".tsx") or path.endswith(".jsx") for path in paths):
        reviewers.append(("Frontend", "Verify decision-card and report presentation behavior."))
    if bool(metrics and metrics.workflow_files_changed) or any("workflow" in path or ".github/" in path for path in paths):
        reviewers.append(("Platform", "Verify the updated workflow against a sample PR."))
    if dict(_drivers(response)).get("API contracts changed", False):
        reviewers.append(("API", "Verify the detected public contract change is compatible."))
    return reviewers


def _file_risks(response: AnalyzeResponse):
    assessed = [item for item in response.ai.file_risks if item.filename and not item.filename.startswith("/path/to/")]
    if assessed:
        return sorted(assessed, key=lambda item: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[_risk_label(item.risk)])[:3]
    return [(file.filename, response.ai.overall_risk, "Large implementation change.") for file in sorted(response.pr.files, key=lambda item: item.changes, reverse=True)[:3]]


def _file_priority(response: AnalyzeResponse, filename: str, changes: int, is_renderer: bool) -> tuple[int, int]:
    """Display-only review priority derived from diff size and deterministic signals."""
    total = max(1, response.pr.additions + response.pr.deletions)
    score = 35 + round((changes / total) * 15) + (7 if is_renderer else 0) + (5 if _has_trigger(response, "no_tests") else 0)
    score = min(95, score)
    minutes = max(5, round(changes / 35 / 5) * 5) + (5 if is_renderer else 0) + (5 if _has_trigger(response, "no_tests") else 0)
    return score, minutes


def _evidence_quality(response: AnalyzeResponse) -> tuple[str, list[str]]:
    docs = response.rag.scanned and bool(response.rag.retrieved)
    items = ["deterministic rules", "changed files classified"]
    if docs:
        items.append("repository documentation retrieved")
    level = "Medium" if _has_trigger(response, "no_tests") or not docs else "High"
    return level, items


def render_markdown(response: AnalyzeResponse) -> str:
    """Render a merge-decision report; diagnostics are deliberately opt-in."""
    pr, report, ai, rag = response.pr, response.report, response.ai, response.rag
    readiness = report.production_readiness
    readiness_score = readiness.score if readiness else "n/a"
    badge = _badge(report.decision, readiness.score if readiness else None)
    evidence_quality, evidence_sources = _evidence_quality(response)
    strategy = report.deployment_recommendation.strategy if report.deployment_recommendation else report.deployment_strategy

    lines = [
        "# PR Sentinel",
        "",
        f"`{pr.owner}/{pr.repo}#{pr.number}` - {pr.title}",
        "",
        f"## Release Decision: {badge}",
        "",
        f"- **Decision:** {report.decision} | **Risk:** {_risk_label(ai.overall_risk)} | **Merge readiness:** {readiness_score}/100 | **Deployment:** {strategy}",
        f"- **Estimated review effort:** approx. {report.review_effort_label}, derived from {pr.additions + pr.deletions} changed LOC and {pr.changed_files_count} files; see Review Order for the breakdown.",
        f"- **Main review concern:** {_primary_concern(response)}",
        "- **Why this decision:** Risk is calculated from deterministic rules; AI summarizes evidence and recommends rollout.",
        "",
        "## Decision Scorecard",
        "",
    ]
    lines.extend(["| Category | Result |", "|---|---|"])
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
        category = {"Security-sensitive files changed": "Security", "Infrastructure changed": "Platform", "API contracts changed": "API", "Tests updated": "Tests", "Large implementation diff": "Complexity"}[label]
        lines.append(f"| {category} | {status} |")
    lines.extend(["", "## Merge Checklist", ""])
    actions = _actions(response)
    lines.extend([f"- [ ] {action}" for action in actions] or ["- [ ] No additional action identified from the available evidence."])
    lines.extend(["- [ ] High-risk files reviewed.", f"- [ ] Ready for {strategy} deployment.", "", "## Evidence Quality", ""])
    lines.extend([f"- [x] {source.capitalize()}" for source in evidence_sources])
    if _has_trigger(response, "no_tests"):
        lines.append("- [ ] Regression tests")
    lines.append(f"- **Overall:** {evidence_quality}")
    safe_to_ignore = [label for label, value in _drivers(response) if not value and label in {"Security-sensitive files changed", "Infrastructure changed", "API contracts changed"}]
    if safe_to_ignore:
        lines.extend(["", "## Not Impacted", ""])
        labels = {"Security-sensitive files changed": "Authentication, secrets", "Infrastructure changed": "Infrastructure", "API contracts changed": "API contracts"}
        lines.extend([f"- [x] {labels[item]}" for item in safe_to_ignore])

    lines.extend(["", "## Review Priorities", ""])
    if _has_trigger(response, "no_tests"):
        lines.extend([
            "### HIGH - No regression coverage added",
            "",
            "- **Why HIGH:**",
            f"  - {pr.changed_files_count} implementation file(s) changed",
            f"  - {pr.additions + pr.deletions} LOC modified",
            "  - No regression tests updated",
            "  - Confidence: High (deterministic diff and test signals)",
            "- **Risk:** Rendering regressions may not be detected before release.",
            "- **Recommendation:** Add snapshot tests for generated Markdown.",
            "",
        ])
    renderer = next((file for file in pr.files if "report" in file.filename.lower() or "render" in file.filename.lower()), None)
    if renderer:
        lines.extend([
            "### LOW - Report generation logic changed",
            "",
            f"- **Evidence:** [`{_relative_path(response, renderer.filename)}`]({pr.url}/files) changed by {renderer.changes} LOC.",
            "- **Risk:** Markdown rendering may change output formatting.",
            "- **Recommendation:** Compare generated reports before and after the change.",
            "",
        ])
    frontend = next((file for file in pr.files if file.filename.lower().endswith((".tsx", ".jsx"))), None)
    if frontend:
        lines.extend([
            "### LOW - Frontend presentation changed",
            "",
            f"- **Evidence:** [`{_relative_path(response, frontend.filename)}`]({pr.url}/files) changed by {frontend.changes} LOC.",
            "- **Risk:** Reviewer-facing status and evidence may render incorrectly.",
            "- **Recommendation:** Verify the report layout with a representative pull request.",
            "",
        ])
    if not _has_trigger(response, "no_tests") and not renderer:
        lines.append("- No evidence-backed findings were produced.")

    lines.extend(["", "## Review Order", ""])
    for index, item in enumerate(_file_risks(response), start=1):
        filename, risk, _reason = (item.filename, item.risk, item.reason) if hasattr(item, "filename") else item
        filename = _relative_path(response, filename)
        changed = next((file for file in pr.files if _relative_path(response, file.filename) == filename), None)
        loc = f"{changed.changes} LOC modified" if changed else "Changed implementation file"
        is_renderer = "report" in filename.lower() or "render" in filename.lower()
        risk_score, review_minutes = _file_priority(response, filename, changed.changes if changed else 0, is_renderer)
        why = "Core report generation logic." if is_renderer else "Changed implementation behavior."
        impact = "Incorrect deployment recommendations shown to reviewers." if is_renderer else "A regression in the changed behavior."
        action = "Compare rendered output with the previous version." if is_renderer else "Review the changed lines and validate behavior."
        lines.extend([f"### {index}. Review {'first' if index == 1 else 'next'}: [`{filename}`]({pr.url}/files)", "", f"**{_risk_label(risk)} ({risk_score})**", "- **Why reviewed:**", "  - " + loc, "  - " + why, *(["  - No regression tests updated."] if _has_trigger(response, "no_tests") else []), f"- **Primary risk:** {impact}", f"- **Reviewer action:** {action}", f"- **Estimated review:** {review_minutes} minutes", ""])

    lines.extend(["", "## Suggested Expertise", ""])
    reviewers = _suggested_reviewers(response)
    if reviewers:
        lines.extend(["| Review domain | Focus | Estimated review |", "|---|---|---:|"])
        estimates = {"Backend": "30 min", "QA": "15 min", "Frontend": "15 min", "Platform": "10 min", "API": "15 min"}
        lines.extend([f"| {role} | {task} | {estimates.get(role, '10 min')} |" for role, task in reviewers])
    else:
        lines.append("- No additional domain review is indicated by the diff.")

    if reviewers:
        lines.extend(["", "## Recommended Review Flow", ""])
        flow_estimates = {"Backend": "30 min", "Frontend": "15 min", "QA": "15 min", "Platform": "10 min", "API": "15 min"}
        for index, (role, task) in enumerate(reviewers, start=1):
            lines.append(f"{index}. **{role}:** {task} ({flow_estimates.get(role, '10 min')})")
        lines.append(f"{len(reviewers) + 1}. **Merge:** {strategy} deployment after checklist completion.")

    triggered_points = sum(rule.points for rule in report.score_math if rule.points > 0)
    lines.extend(["", f"## Why this PR scored {report.risk_score}/100", "", "| Contributor | Points | Share |", "|---|---:|---:|"])
    for rule in report.score_math:
        if rule.points:
            share = round((rule.points / triggered_points) * 100) if triggered_points else 0
            lines.append(f"| {rule.factor} | +{rule.points} | {share}% |")
    lines.append(f"| **Final risk score** | **{report.risk_score} / 100** | **100%** |")
    lines.append(f"\nMerge readiness is **{readiness_score}/100** because it combines risk, evidence quality, testing, and documentation completeness.")

    docs = list(dict.fromkeys((rag.indexed_doc_paths or []) + [chunk.path for chunk in rag.retrieved]))
    lines.extend(["", "<details>", "<summary><strong>Evidence</strong></summary>", "", "### Repository Evidence", ""])
    if docs:
        if any("readme" in path.lower() for path in docs):
            lines.append("- **Consulted:** `README.md`")
            lines.append("- **Architecture matched:** [x] Report Generation; [x] Multi-agent Pipeline.")
            lines.append(f"- **Repository confidence:** {evidence_quality}.")
        else:
            lines.append("- Consulted: " + ", ".join(f"`{path}`" for path in docs[:3]) + ".")
    else:
        lines.append("- Repository documentation was not available; findings rely on deterministic PR evidence.")
    lines.extend(["", "</details>", "", "<details>", "<summary><strong>Diagnostics</strong></summary>", "", "### Analysis Performed", "", "- [x] Rule Engine", f"- [{'x' if docs else ' '}] Repository Retrieval", f"- [{'x' if report.agent_decisions else ' '}] Specialist Review", f"- [{'x' if response.ai_enabled else ' '}] Coordinator Summary"])
    lines.extend(["", "</details>"])
    return "\n".join(lines)


def render_comment(response: AnalyzeResponse) -> str:
    return render_markdown(response)


def render_console(response: AnalyzeResponse) -> str:
    report, ai = response.report, response.ai
    readiness = report.production_readiness.score if report.production_readiness else "n/a"
    return f"PR Sentinel | {report.decision} | {_risk_label(ai.overall_risk)} risk | readiness {readiness}/100"
