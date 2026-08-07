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


def _perspective_status(decision: str) -> str:
    decision = decision.lower()
    if "concern" in decision or "block" in decision or "fail" in decision:
        return "WARN"
    if "skip" in decision:
        return "PASS"
    return "PASS"


_PERSPECTIVE_NAMES = {
    "database": "Backend",
    "security": "Security",
    "tests": "QA",
    "performance": "SRE",
    "api": "API",
}


def render_markdown(response: AnalyzeResponse) -> str:
    """Render a compact, evidence-first GitHub PR report.

    Raw scoring, retrieval and execution diagnostics remain available below the
    fold so the default comment stays usable during a fast review.
    """
    pr, report, ai, rag = response.pr, response.report, response.ai, response.rag
    readiness = report.production_readiness
    readiness_score = readiness.score if readiness else None
    confidence = report.confidence_explanation.level if report.confidence_explanation else _confidence_label(report.confidence)
    strategy = report.deployment_recommendation.strategy if report.deployment_recommendation else report.deployment_strategy
    badge = _badge(report.decision, readiness_score)
    findings = sorted(
        (item for category in report.risk_categories for item in category.evidence),
        key=lambda item: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[_risk_label(item.severity)],
    )[:5]
    file_risks = sorted(ai.file_risks, key=lambda item: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[_risk_label(item.risk)])[:3]

    lines = [
        "# PR Sentinel - Deployment Risk Report",
        "",
        f"**[{badge}]**  `{pr.owner}/{pr.repo}#{pr.number}` - {pr.title}",
        "",
        "## Decision",
        "",
        "| Decision | Risk | Confidence | Merge readiness | Deployment |",
        "|---|---|---|---|---|",
        f"| **{report.decision}** | **{_risk_label(ai.overall_risk)}** | **{confidence}** | **{readiness_score if readiness_score is not None else 'n/a'}/100** | **{strategy}** |",
        "",
        "## Executive Summary",
        "",
        _summary(report.executive_summary or report.summary, ai.summary),
        "",
        "## Top Findings",
        "",
    ]
    if findings:
        for item in findings:
            severity = {"HIGH": "Critical", "MEDIUM": "Warning", "LOW": "Info"}[_risk_label(item.severity)]
            lines.append(f"- **{severity}** - [`{item.file_path}`]({pr.url}/files): {item.explanation} **Action:** {item.recommended_action}")
    else:
        lines.append("- **Info** - No evidence-backed risk findings were produced.")
    lines.extend(["", "## Highest-Risk Files", ""])
    if file_risks:
        for item in file_risks:
            action = next((e.recommended_action for e in findings if e.file_path == item.filename), "Review the changed lines and validate the affected behavior.")
            lines.append(f"- [`{item.filename}`]({pr.url}/files) - **{_risk_label(item.risk)}**: {item.reason} **Action:** {action}")
    else:
        lines.append("- No files were individually flagged by the available evidence.")

    lines.extend(["", "## Required Before Merge", ""])
    if report.operational_checklist:
        for item in report.operational_checklist:
            lines.append(f"- [ ] {item.task}")
    else:
        lines.append("- [ ] No additional mandatory action was identified from the available evidence.")

    explanation = "Derived from risk, evidence quality, test coverage, and documentation completeness."
    lines.extend(["", "## Merge Readiness", "", f"**{readiness_score if readiness_score is not None else 'n/a'}/100** - {readiness.label if readiness else 'Not calculated'}. {explanation}", "", "## Review Perspectives", "", "| Perspective | Status | Evidence-backed view |", "|---|---|---|"])
    decisions_by_perspective = {_PERSPECTIVE_NAMES.get(item.agent): item for item in report.agent_decisions}
    for perspective in ("Backend", "Security", "QA", "SRE", "API"):
        decision = decisions_by_perspective.get(perspective)
        if decision:
            lines.append(f"| {perspective} | **{_perspective_status(decision.decision)}** | {decision.reasoning or 'No additional reasoning recorded.'} |")
        else:
            lines.append(f"| {perspective} | **WARN** | No specialist evidence was available for this perspective. |")

    docs = rag.indexed_doc_paths or []
    lines.extend(["", "## Evidence", ""])
    if docs:
        lines.append("- Repository documentation used: " + ", ".join(f"`{path}`" for path in docs[:5]))
    elif not rag.scanned:
        lines.append(f"- **Evidence gap:** Repository documentation was unavailable ({rag.skip_reason or 'not retrieved'}).")
    else:
        lines.append("- **Evidence gap:** No repository documentation matched this diff closely enough to cite.")
    if response.judge and not response.judge.grounded:
        lines.append("- **Evidence gap:** Groundedness review found unsupported claims; inspect Technical Details before relying on them.")
    if not response.ai_enabled:
        lines.append("- Analysis used deterministic heuristics only; AI-generated claims are unavailable.")

    lines.extend(["", "<details>", "<summary><strong>Technical Details</strong> (raw evidence, scoring, and diagnostics)</summary>", ""])
    if report.score_math:
        lines.extend(["### Deterministic Score Evidence", ""])
        for item in report.score_math:
            lines.append(f"- `{item.factor}` ({item.points:+d}): {item.reason}")
        lines.append("")
    if report.agent_decisions:
        lines.extend(["### Detailed Review Reasoning", ""])
        for decision in report.agent_decisions:
            lines.append(f"- **{decision.label}** ({decision.decision}, {decision.confidence}% confidence, {decision.execution_time_ms}ms): {decision.reasoning or 'No further reasoning recorded.'}")
        lines.append("")
    if rag.retrieved:
        lines.extend(["### Repository Context", ""])
        for chunk in rag.retrieved[:5]:
            lines.append(f"- **`{chunk.path}`** (similarity {chunk.score:.2f}): {chunk.snippet[:240]}")
        lines.append("")
    if report.execution_metrics:
        lines.extend(["### Execution Diagnostics", "", f"- Total analysis time: {report.execution_metrics.total_duration_ms}ms", ""])
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
