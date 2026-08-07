from __future__ import annotations

from .models import AnalyzeResponse, RiskLevel
from .config import get_settings


def _risk_label(level: RiskLevel | str) -> str:
    return level.value if isinstance(level, RiskLevel) else str(level)


def _confidence_level(score: int) -> str:
    return "High" if score >= 75 else "Medium" if score >= 50 else "Low"


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
        ("Infrastructure changed", bool(metrics and metrics.workflow_files_changed) or any("workflow" in path or "actions/" in path or "terraform" in path or "k8s/" in path for path in paths)),
        ("API contracts changed", bool(metrics and metrics.public_apis_modified) and api_evidence),
        ("Tests updated", bool(metrics and metrics.test_files_touched)),
        ("Large implementation diff", _has_trigger(response, "large_diff", "medium_diff")),
    ]


def _primary_concern(response: AnalyzeResponse) -> str:
    if _has_trigger(response, "no_tests"):
        return "Implementation changed without corresponding test updates."
    factor = next((item.reason for item in response.heuristics.factors if item.triggered), None)
    return factor or "Review the evidence-backed findings before merging."


def _summary(response: AnalyzeResponse, badge: str) -> str:
    paths = [file.filename.lower() for file in response.pr.files]
    report_changed = any("report" in path or "render" in path for path in paths)
    ui_changed = any(path.endswith(".tsx") or path.endswith(".ts") for path in paths)
    changed = "This PR modifies the report rendering pipeline" + (" and frontend UI." if ui_changed else ".") if report_changed else "This PR modifies implementation files."
    api_changed = dict(_drivers(response)).get("API contracts changed", False)
    clear = "API contract changes need review." if api_changed else "No security or public API contract changes were detected."
    merge = "Merge after the required checks pass." if badge != "DO NOT MERGE" else "Do not merge until the blocking evidence is resolved."
    words = f"{changed} {clear} The primary concern is missing regression coverage. {merge}".split()
    return " ".join(words[:50])


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


def render_markdown(response: AnalyzeResponse) -> str:
    """Render a merge-decision report; diagnostics are deliberately opt-in."""
    pr, report, ai, rag = response.pr, response.report, response.ai, response.rag
    readiness = report.production_readiness
    readiness_score = readiness.score if readiness else "n/a"
    confidence = report.confidence
    badge = _badge(report.decision, readiness.score if readiness else None)
    strategy = report.deployment_recommendation.strategy if report.deployment_recommendation else report.deployment_strategy
    findings = sorted((item for category in report.risk_categories for item in category.evidence), key=lambda item: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[_risk_label(item.severity)])[:5]

    lines = [
        "# PR Sentinel",
        "",
        f"`{pr.owner}/{pr.repo}#{pr.number}` - {pr.title}",
        "",
        f"## {badge}",
        "",
        f"- **Decision:** {report.decision} | **Risk:** {_risk_label(ai.overall_risk)} | **Merge readiness:** {readiness_score}/100 | **Deployment:** {strategy}",
        f"- **Primary concern:** {_primary_concern(response)}",
        f"- **Confidence:** {confidence}% ({_confidence_level(confidence)}) - lower because missing regression tests, a large implementation refactor, and {'partial' if not rag.scanned or not rag.retrieved else 'available'} repository documentation evidence.",
        f"- **Estimated review effort:** {report.review_effort_label} | **Key review files:** {len(_file_risks(response))} | **Blocking findings:** {sum(1 for item in findings if _risk_label(item.severity) == 'HIGH')}",
        "",
        "## Decision Drivers",
        "",
    ]
    lines.extend(["| Signal | Status |", "|---|---|"])
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
            status = "FAIL - No test updates"
        elif value:
            status = "WARN - Large" if label == "Large implementation diff" else "WARN - Changed"
        else:
            status = f"OK - {positive if label == 'Security-sensitive files changed' else 'No changes'}"
        lines.append(f"| {label.replace(' files changed', '').replace(' implementation', '')} | {status} |")
    lines.extend(["", "## Summary", "", _summary(response, badge), "", "## Required Before Merge", ""])
    actions = _actions(response)
    lines.extend([f"- [ ] {action}" for action in actions] or ["- [ ] No additional action identified from the available evidence."])

    lines.extend(["", "## Top Findings", ""])
    if findings:
        for item in findings:
            severity = {"HIGH": "Critical", "MEDIUM": "Warning", "LOW": "Info"}[_risk_label(item.severity)]
            evidence = _relative_path(response, item.file_path) if item.file_path and not item.file_path.startswith("(") else "deterministic rule"
            lines.extend([f"- **{severity}:** {item.explanation}", f"  - **Evidence:** [`{evidence}`]({pr.url}/files)", f"  - **Action:** {item.recommended_action}"])
    else:
        lines.append("- **Info:** No evidence-backed findings were produced.")

    lines.extend(["", "## Highest-Risk Files", ""])
    for item in _file_risks(response):
        filename, risk, _reason = (item.filename, item.risk, item.reason) if hasattr(item, "filename") else item
        filename = _relative_path(response, filename)
        changed = next((file for file in pr.files if _relative_path(response, file.filename) == filename), None)
        loc = f"{changed.changes} LOC modified" if changed else "Changed implementation file"
        is_renderer = "report" in filename.lower() or "render" in filename.lower()
        why = "Core report generation logic." if is_renderer else "Changed implementation behavior."
        impact = "Incorrect deployment recommendations shown to reviewers." if is_renderer else "A regression in the changed behavior."
        action = "Compare rendered output with the previous version." if is_renderer else "Review the changed lines and validate behavior."
        lines.extend([f"- [`{filename}`]({pr.url}/files) - **{_risk_label(risk)}**", f"  - **Why reviewed:** {loc}; {why}{' No regression tests updated.' if _has_trigger(response, 'no_tests') else ''}", f"  - **Production impact:** {impact}", f"  - **Review:** {action}"])

    lines.extend(["", "## Suggested Reviewers", ""])
    reviewers = _suggested_reviewers(response)
    if reviewers:
        lines.extend(["| Reviewer | Focus |", "|---|---|"])
        lines.extend([f"| {role} | {task} |" for role, task in reviewers])
    else:
        lines.append("- No additional domain review is indicated by the diff.")

    lines.extend(["", "## Merge Readiness", "", f"**Final score: {readiness_score}/100** - {readiness.label if readiness else 'Not calculated'}."])
    if readiness:
        lines.extend([f"- {deduction}" for deduction in readiness.deductions])

    docs = list(dict.fromkeys((rag.indexed_doc_paths or []) + [chunk.path for chunk in rag.retrieved]))
    lines.extend(["", "<details>", "<summary><strong>Evidence</strong></summary>", "", "### Repository Evidence", ""])
    if docs:
        if any("readme" in path.lower() for path in docs):
            lines.append("- **README.md:** Defines the report generation architecture.")
            lines.append("- Used to validate ownership of the modified rendering files.")
        else:
            lines.append("- Consulted: " + ", ".join(f"`{path}`" for path in docs[:3]) + ".")
    else:
        lines.append("- Repository documentation was not available; findings rely on deterministic PR evidence.")
    lines.extend(["", "### Triggered Rules", "", "| Rule | Weight | Evidence |", "|---|---:|---|"])
    for rule in report.score_math:
        if rule.points:
            lines.append(f"| {rule.factor} | +{rule.points} | {rule.reason} |")
    lines.extend(["", "</details>", "", "<details>", "<summary><strong>Diagnostics</strong></summary>", "", "| Diagnostic | Value |", "|---|---|"])
    lines.append(f"| LLM | {get_settings().ollama_model if response.ai_enabled else 'Not used'} |")
    lines.append(f"| RAG | {len(docs)} document(s) |")
    lines.append(f"| Agents | {len(report.agent_decisions)} |")
    if report.execution_metrics:
        lines.append(f"| Runtime | {round(report.execution_metrics.total_duration_ms / 1000)} sec |")
    lines.extend(["", "</details>", "", "*Claims are tied to PR diff evidence, repository documentation, or deterministic heuristics.*"])
    return "\n".join(lines)


def render_comment(response: AnalyzeResponse) -> str:
    return render_markdown(response)


def render_console(response: AnalyzeResponse) -> str:
    report, ai = response.report, response.ai
    readiness = report.production_readiness.score if report.production_readiness else "n/a"
    return f"PR Sentinel | {report.decision} | {_risk_label(ai.overall_risk)} risk | readiness {readiness}/100"
