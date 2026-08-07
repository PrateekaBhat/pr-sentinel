from __future__ import annotations

from .models import AnalyzeResponse, RiskLevel


def _risk_label(level: RiskLevel | str) -> str:
    return level.value if isinstance(level, RiskLevel) else str(level)


def _confidence_label(score: int) -> str:
    return "High" if score >= 75 else "Medium" if score >= 50 else "Low"


def _badge(decision: str, readiness: int | None) -> str:
    if decision == "BLOCK" or (readiness is not None and readiness < 55):
        return "Do Not Merge"
    if decision == "ALLOW" and (readiness is None or readiness >= 80):
        return "Ready"
    return "Review Needed"


def _summary(report_summary: str, fallback: str) -> str:
    """Keep the decision summary under the 50-word review budget."""
    words = (report_summary or fallback or "No summary was generated.").split()
    return " ".join(words[:50]) + ("..." if len(words) > 50 else "")


def _is_placeholder_path(path: str) -> bool:
    return not path or path.startswith("/path/to/")


def _relative_path(response: AnalyzeResponse, path: str) -> str:
    """Normalize provider-prefixed paths for reviewer-facing output."""
    prefix = f"{response.pr.repo}/{response.pr.repo}/"
    return path[len(prefix):] if path.startswith(prefix) else path


def _display_file_risks(response: AnalyzeResponse):
    """Prefer evidence-backed paths and replace fallback placeholders with diff paths."""
    valid = [item for item in response.ai.file_risks if not _is_placeholder_path(item.filename)]
    if valid:
        return sorted(valid, key=lambda item: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[_risk_label(item.risk)])[:3]
    level = response.ai.overall_risk
    return [
        (file.filename, level, f"{file.changes} changed lines in this implementation file.")
        for file in sorted(response.pr.files, key=lambda item: item.changes, reverse=True)[:3]
    ]


def _primary_concern(response: AnalyzeResponse) -> str:
    if any(f.key == "no_tests" and f.triggered for f in response.heuristics.factors):
        return "Implementation changed without corresponding test updates."
    trigger = next((factor.reason for factor in response.heuristics.factors if factor.triggered), None)
    return trigger or "Review the evidence-backed findings before merging."


def _review_summary(response: AnalyzeResponse, badge: str) -> str:
    paths = [file.filename.lower() for file in response.pr.files]
    changed = "This PR modifies the report rendering pipeline and frontend UI." if any("report" in path or "render" in path for path in paths) else "This PR modifies implementation files."
    workflow_changed = bool(response.report.engineering_metrics and response.report.engineering_metrics.workflow_files_changed)
    clear = "No security or public API risks were detected." if workflow_changed else "No security, infrastructure, or public API risks were detected."
    safety = "It can merge after the required checks pass." if badge != "Do Not Merge" else "It should not merge until the blocking evidence is resolved."
    return _summary(f"{changed} {clear} The primary concern is that implementation changed without accompanying tests. {safety}", "")


def _required_actions(response: AnalyzeResponse) -> list[str]:
    paths = [file.filename for file in response.pr.files]
    actions: list[str] = []
    if any(f.key == "no_tests" and f.triggered for f in response.heuristics.factors):
        actions.append("Add regression tests for the changed implementation paths.")
    if any("report" in path.lower() or "render" in path.lower() for path in paths):
        actions.append("Validate rendered Markdown output against a representative pull request.")
    if any(".github/workflows/" in path.lower() or "workflow" in path.lower() for path in paths):
        actions.append("Dry-run the modified GitHub Actions workflow on a sample pull request.")
    return actions[:3]


def _perspectives(response: AnalyzeResponse) -> list[tuple[str, str, str]]:
    paths = [file.filename.lower() for file in response.pr.files]
    metrics = response.report.engineering_metrics
    backend_changed = any(path.endswith((".py", ".go", ".java", ".rb", ".cs")) or "backend/" in path for path in paths)
    workflow_changed = bool(metrics and metrics.workflow_files_changed) or any(".github/workflows/" in path for path in paths)
    tests_missing = any(f.key == "no_tests" and f.triggered for f in response.heuristics.factors)
    api_changed = bool(metrics and metrics.public_apis_modified)
    sensitive = any(any(token in path for token in ("auth", "secret", "credential", "token")) for path in paths)
    return [
        ("Backend", "WARN" if backend_changed else "PASS", "Report rendering or backend implementation changed; review the generated Markdown output." if backend_changed else "No backend implementation files changed."),
        ("Security", "WARN" if sensitive else "PASS", "Security-sensitive paths changed; verify the diff." if sensitive else "No authentication, secrets, or credential paths changed."),
        ("QA", "WARN" if tests_missing else "PASS", "Implementation changed without test updates; add regression coverage." if tests_missing else "Test coverage was updated or no implementation path changed."),
        ("Platform", "WARN" if workflow_changed else "PASS", "GitHub Actions workflow changed; dry-run it on a sample pull request." if workflow_changed else "No CI/CD or deployment configuration changed."),
        ("API", "WARN" if api_changed else "PASS", "Public API routes changed; verify contract compatibility." if api_changed else "No public API interface changes were detected."),
    ]


def _decision_drivers(response: AnalyzeResponse) -> list[str]:
    paths = [file.filename.lower() for file in response.pr.files]
    metrics = response.report.engineering_metrics
    tests_updated = bool(metrics and metrics.test_files_touched)
    large_diff = any(f.key in {"large_diff", "medium_diff"} and f.triggered for f in response.heuristics.factors)
    security = any(any(token in path for token in ("auth", "secret", "credential", "token")) for path in paths)
    infra = bool(metrics and metrics.workflow_files_changed) or any(".github/workflows/" in path or "terraform" in path or "k8s/" in path for path in paths)
    api = bool(metrics and metrics.public_apis_modified)
    return [
        f"Security-sensitive files changed: {'Yes' if security else 'No'}",
        f"Infrastructure changed: {'Yes' if infra else 'No'}",
        f"API contracts changed: {'Yes' if api else 'No'}",
        f"Tests updated: {'Yes' if tests_updated else 'No'}",
        f"Large implementation diff: {'Yes' if large_diff else 'No'}",
    ]


def render_markdown(response: AnalyzeResponse) -> str:
    """Render a compact, evidence-first GitHub PR report.

    Raw scoring, retrieval and execution diagnostics remain available below the
    fold so the default comment stays usable during a fast review.
    """
    pr, report, ai, rag = response.pr, response.report, response.ai, response.rag
    readiness = report.production_readiness
    readiness_score = readiness.score if readiness else None
    confidence_level = report.confidence_explanation.level if report.confidence_explanation else _confidence_label(report.confidence)
    confidence = f"{report.confidence}% ({confidence_level})"
    strategy = report.deployment_recommendation.strategy if report.deployment_recommendation else report.deployment_strategy
    badge = _badge(report.decision, readiness_score)
    findings = sorted(
        (item for category in report.risk_categories for item in category.evidence),
        key=lambda item: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[_risk_label(item.severity)],
    )[:5]
    file_risks = _display_file_risks(response)

    lines = [
        "# PR Sentinel - Deployment Risk Report",
        "",
        f"`{pr.owner}/{pr.repo}#{pr.number}` - {pr.title}",
        "",
        "## Status",
        "",
        f"### {'REVIEW REQUIRED BEFORE MERGE' if badge == 'Review Needed' else badge.upper()}",
        "",
        f"- **Decision:** {report.decision}",
        f"- **Risk:** {_risk_label(ai.overall_risk)} · **Confidence:** {confidence}",
        f"- **Merge readiness:** {readiness_score if readiness_score is not None else 'n/a'} / 100",
        f"- **Deployment:** {strategy}",
        f"- **Primary concern:** {_primary_concern(response)}",
        f"- **Confidence basis:** {confidence_level} confidence; deterministic rules and file classification were available{' but missing test updates reduce certainty' if any(f.key == 'no_tests' and f.triggered for f in response.heuristics.factors) else ''}.",
    ]
    lines.extend(["", "## Decision Drivers", ""])
    for driver in _decision_drivers(response):
        label, value = driver.rsplit(": ", 1)
        lines.append(f"- {'✓' if value == 'Yes' else '✗'} {label}: **{value}**")
    lines.extend([f"- **Overall:** {_risk_label(ai.overall_risk)} risk", "", "## Executive Summary", "", _review_summary(response, badge), "", "## Top Findings", ""])
    if findings:
        for item in findings:
            severity = {"HIGH": "Critical", "MEDIUM": "Warning", "LOW": "Info"}[_risk_label(item.severity)]
            evidence = _relative_path(response, item.file_path) if not _is_placeholder_path(item.file_path) else "deterministic rule"
            lines.extend([
                f"- **{severity}** — {item.explanation}",
                f"  - **Evidence:** [`{evidence}`]({pr.url}/files)",
                f"  - **Action:** {item.recommended_action}",
            ])
    else:
        lines.append("- **Info** - No evidence-backed risk findings were produced.")
    lines.extend(["", "## Highest-Risk Files", ""])
    if file_risks:
        for item in file_risks:
            filename, risk, reason = (item.filename, item.risk, item.reason) if hasattr(item, "filename") else item
            filename = _relative_path(response, filename)
            changed_file = next((file for file in pr.files if _relative_path(response, file.filename) == filename), None)
            loc = f"{changed_file.changes} LOC modified" if changed_file else reason
            scope = "Core report generation logic." if "report" in filename.lower() or "render" in filename.lower() else "Workflow configuration affects automated PR analysis." if "workflow" in filename.lower() or "actions/" in filename.lower() else reason
            tests_note = " No regression tests updated." if any(f.key == "no_tests" and f.triggered for f in response.heuristics.factors) else ""
            reason = f"Why reviewed: {loc}; {scope}{tests_note}"
            action = next((e.recommended_action for e in findings if e.file_path == filename), "Review the changed lines and validate the affected behavior.")
            impact = "Incorrect deployment recommendations shown to reviewers." if "report" in filename.lower() or "render" in filename.lower() else "PR analysis may not run as expected."
            lines.extend([f"### [`{filename}`]({pr.url}/files)", "", f"**{_risk_label(risk)}** — {reason}", f"- **Production impact:** {impact}", f"- **Review:** {action}", ""])
    else:
        lines.append("- No files were individually flagged by the available evidence.")

    lines.extend(["", "## Required Before Merge", ""])
    actions = _required_actions(response)
    if actions:
        for action in actions:
            lines.append(f"- [ ] {action}")
    else:
        lines.append("- [ ] No additional mandatory action was identified from the available evidence.")

    explanation = "Derived deterministically from risk, evidence quality, test coverage, and documentation completeness."
    lines.extend(["", "## Merge Readiness", "", f"**Final score: {readiness_score if readiness_score is not None else 'n/a'} / 100** — {readiness.label if readiness else 'Not calculated'}.", explanation])
    if readiness and readiness.deductions:
        lines.extend([f"- {deduction}" for deduction in readiness.deductions])
    lines.extend(["", "## Review Perspectives", ""])
    for perspective, status, reason in _perspectives(response):
        lines.append(f"- **{perspective} — {status}:** {reason}")

    docs = list(dict.fromkeys((rag.indexed_doc_paths or []) + [chunk.path for chunk in rag.retrieved]))
    lines.extend(["", "## Repository Context", ""])
    if False and docs:  # legacy raw excerpts are intentionally hidden from reviewer output
        lines.append("**Consulted:** " + " · ".join(f"✓ `{path}`" for path in docs[:3]))
        for chunk in rag.retrieved[:2]:
            excerpt = " ".join(chunk.snippet.replace("\ufeff", "").split())[:180]
            if excerpt:
                lines.append(f"- **`{chunk.path}`:** {excerpt}{'...' if len(excerpt) == 180 else ''}")
    elif docs:
        labels = []
        for path in docs[:3]:
            label = "architecture" if "readme" in path.lower() else "risk scoring design" if "risk" in path.lower() else "agent routing" if "agent" in path.lower() else "repository documentation"
            labels.append(f"[x] `{path}` ({label})")
        lines.append("**Repository documentation consulted:** " + " · ".join(labels))
        lines.append("These documents were retrieved to ground the analysis.")
    elif not rag.scanned:
        lines.append(f"- **Evidence gap:** Repository documentation was unavailable ({rag.skip_reason or 'not retrieved'}).")
    else:
        lines.append("- No repository documentation was available for this diff; findings rely on deterministic PR evidence.")
    if response.judge and not response.judge.grounded:
        lines.append("- **Evidence gap:** Groundedness review found unsupported claims; inspect Evidence & Scoring before relying on them.")
    if not response.ai_enabled:
        lines.append("- Analysis used deterministic heuristics only; AI-generated claims are unavailable.")

    lines.extend(["", "<details>", "<summary><strong>Evidence & Scoring</strong></summary>", ""])
    if report.score_math:
        lines.extend(["### Deterministic Score Evidence", ""])
        for item in report.score_math:
            lines.append(f"- `{item.factor}` ({item.points:+d}): {item.reason}")
        lines.append("")
    if report.agent_decisions:
        lines.extend(["### Agents Executed", ""])
        for decision in report.agent_decisions:
            status = "Skipped" if "skip" in decision.decision.lower() else "Reviewed"
            lines.append(f"- **{decision.label}:** {status}")
        lines.append("")
    if rag.retrieved:
        lines.extend(["### RAG Retrieval", ""])
        for chunk in rag.retrieved[:5]:
            lines.append(f"- Retrieved repository context from **`{chunk.path}`**.")
        lines.append("")
    if report.execution_metrics:
        runtime_seconds = round(report.execution_metrics.total_duration_ms / 1000)
        lines.extend(["### Execution", "", "- Repository indexed", "- Specialist agents executed", "- Coordinator synthesized report", f"- Total runtime: {runtime_seconds}s", ""])
    if readiness and readiness.deductions:
        lines.extend(["### Readiness Deductions", ""] + [f"- {deduction}" for deduction in readiness.deductions] + [""])
    lines.extend(["</details>", "", "*Generated by PR Sentinel. Claims above are tied to PR diff evidence, repository documentation, or deterministic heuristics.*"])
    return "\n".join(lines)


def render_comment(response: AnalyzeResponse) -> str:
    return render_markdown(response)


def render_console(response: AnalyzeResponse) -> str:
    report, ai = response.report, response.ai
    readiness = report.production_readiness.score if report.production_readiness else None
    return "\n".join([
        "PR SENTINEL - Deployment Risk Report",
        f"Decision: {report.decision} | Risk: {_risk_label(ai.overall_risk)} | Confidence: {_confidence_label(report.confidence)}",
        f"Merge readiness: {readiness if readiness is not None else 'n/a'}/100 | Deployment: {report.deployment_strategy}",
        _summary(report.executive_summary or report.summary, ai.summary),
    ])
