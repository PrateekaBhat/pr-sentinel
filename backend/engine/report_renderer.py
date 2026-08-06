from __future__ import annotations

from datetime import datetime, timezone

from .models import AnalyzeResponse, RiskLevel


def _risk_label(level: RiskLevel | str) -> str:
    if isinstance(level, RiskLevel):
        return level.value
    return str(level)


def _decision_emoji(decision: str) -> str:
    return "🚫" if decision == "BLOCK" else "✅"


def _format_timestamp(raw: str) -> str:
    """Render an ISO-8601 timestamp (often with microseconds, e.g.
    '2026-08-06T10:04:37.276438+00:00') as a short, human-readable UTC
    string, e.g. 'Aug 6, 2026, 10:04 UTC'. Falls back to the raw value
    (trimmed to whole seconds) if parsing fails."""
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        return f"{dt.strftime('%b %-d, %Y, %H:%M')} UTC"
    except (ValueError, TypeError):
        return raw[:19].replace("T", " ") + " UTC" if len(raw) >= 19 else raw


def _format_duration(ms: int | float) -> str:
    """Render a millisecond duration as a compact, human-readable string.
    Sub-second durations stay in ms (e.g. '820ms'); anything at or above
    one second is shown in seconds (e.g. '4.5s'), and a minute or more
    is shown as 'Xm Ys'."""
    ms = round(ms)
    if ms < 1000:
        return f"{ms}ms"
    seconds = ms / 1000
    if seconds < 60:
        text = f"{seconds:.1f}"
        if text.endswith(".0"):
            text = text[:-2]
        return f"{text}s"
    minutes, rem_seconds = divmod(seconds, 60)
    return f"{int(minutes)}m {rem_seconds:.0f}s"


def render_markdown(response: AnalyzeResponse) -> str:
    """Generate a production engineering risk assessment, in Markdown, suitable for
    GitHub PR comments: explainable (every score traces to evidence), auditable
    (agent-by-agent and RAG-by-RAG breakdown), and free of raw heuristic-speak."""
    pr = response.pr
    report = response.report
    ai = response.ai
    rag = response.rag
    metrics = report.execution_metrics
    generated_raw = metrics.generated_at if metrics else datetime.now(timezone.utc).isoformat()
    generated = _format_timestamp(generated_raw)

    decision_emoji = _decision_emoji(report.decision)

    lines: list[str] = [
        "# PR Sentinel — Release Risk Assessment",
        "",
        f"**Generated:** {generated}  ·  **Repository:** [{pr.repository.full_name}]({pr.url})  ·  **PR:** #{pr.number}",
        "",
        f"### {decision_emoji} {report.decision} — {_risk_label(ai.overall_risk)} risk (score {report.risk_score}/100)",
        "",
        "## Executive Summary",
        "",
        report.executive_summary or report.summary or ai.summary,
        "",
        "| | |",
        "|---|---|",
        f"| **Decision** | `{report.decision}` |",
        f"| **Overall Risk** | `{_risk_label(ai.overall_risk)}` |",
        f"| **Risk Score** | {report.risk_score} / 100 |",
        f"| **Confidence** | {report.confidence_explanation.level if report.confidence_explanation else 'Medium'} ({report.confidence}% — {report.confidence_explanation.evidence_completeness if report.confidence_explanation else 'n/a'} evidence) |",
        f"| **Estimated Review Effort** | ⏱️ `{report.review_effort_label}` |",
        f"| **Recommended Deployment** | `{report.deployment_strategy}` |",
        "",
        "## Pull Request",
        "",
        f"- **Title:** {pr.title}",
        f"- **Author:** @{pr.author}",
        f"- **Branch:** `{pr.head_branch or 'unknown'}` → `{pr.base_branch or report.repository_intelligence.default_branch or 'main'}`",
        f"- **Language / Framework:** {report.repository_intelligence.primary_language or pr.repository.primary_language or 'Unknown'} / "
        f"{report.repository_intelligence.framework or pr.repository.framework or 'Unknown'}",
        f"- **Files Changed:** {pr.changed_files_count} (+{pr.additions}/-{pr.deletions})",
        f"- **Merge Status:** {pr.mergeable_state or 'unknown'}",
        "",
    ]

    # --- Architectural Impact -------------------------------------------------
    impact = report.architectural_impact
    lines.extend(["## Architectural Impact", ""])
    if impact.affected_subsystems:
        lines.append("**Affected subsystems:** " + ", ".join(f"`{s}`" for s in impact.affected_subsystems))
        lines.append("")
    lines.append(impact.narrative or "No clearly affected subsystems were detected.")
    lines.append("")

    # --- Score Calculation Math ------------------------------------------------
    if report.score_math:
        lines.extend(["## Score Calculation Math", ""])
        lines.append("The overall risk score is calculated deterministically from triggered rule weights:")
        lines.append("")
        lines.append("| Factor | Points | Rule / Evidence |")
        lines.append("|---|---|---|")
        for item in report.score_math:
            pts = f"+{item.points}" if item.points > 0 else f"{item.points}"
            lines.append(f"| {item.factor} | `{pts}` | {item.reason} |")
        lines.append(f"| **Total Calculated Score** | **`{report.risk_score}`** | |")
        lines.append("")

    # --- Score breakdown by category -------------------------------------------
    if report.risk_categories:
        lines.extend(["## Risk Score Breakdown", ""])
        lines.append("| Category | Status | Score | Evidence |")
        lines.append("|---|---|---|---|")
        for cat in report.risk_categories:
            lines.append(f"| {cat.category} | `{_risk_label(cat.status)}` | {cat.score}/100 | {len(cat.evidence)} item(s) |")
        lines.append("")

        for cat in report.risk_categories:
            if not cat.evidence:
                continue
            lines.append(f"<details><summary><strong>{cat.category}</strong> — {_risk_label(cat.status)} ({cat.score}/100)</summary>")
            lines.append("")
            lines.append(cat.summary)
            lines.append("")
            for item in cat.evidence:
                conf_lbl = "High" if item.confidence >= 75 else ("Medium" if item.confidence >= 50 else "Low")
                lines.append(f"- **`{item.file_path}`** — {_risk_label(item.severity)} severity ({conf_lbl} confidence)")
                lines.append(f"  - _Why it matters:_ {item.explanation}")
                if item.snippet:
                    lines.append("  - _Evidence:_")
                    lines.append("    ```diff")
                    for l in item.snippet.splitlines():
                        lines.append(f"    {l}")
                    lines.append("    ```")
                lines.append(f"  - _Recommended action:_ {item.recommended_action}")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    # --- LangGraph agent pipeline ------------------------------------------------
    if report.agent_decisions:
        lines.extend(["## Agent Pipeline (LangGraph)", ""])
        lines.append("Each specialist agent only reviews files in its own domain; the coordinator agent")
        lines.append("synthesizes their output (below) into the executive summary and risk breakdown above.")
        lines.append("")
        lines.append("| Agent | Decision | Confidence | Time |")
        lines.append("|---|---|---|---|")
        for d in report.agent_decisions:
            conf_lbl = "High" if d.confidence >= 75 else ("Medium" if d.confidence >= 50 else "Low")
            lines.append(f"| {d.label} | {d.decision} | {conf_lbl} | {_format_duration(d.execution_time_ms)} |")
        lines.append("")
        for d in report.agent_decisions:
            lines.append(f"<details><summary><strong>{d.label}</strong> reasoning</summary>")
            lines.append("")
            lines.append(d.reasoning or "_No further reasoning recorded._")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    # --- RAG pipeline ------------------------------------------------------------
    lines.extend(["## Repository Context (RAG)", ""])
    if rag.scanned:
        cache_label = "cache hit" if rag.cache_hit else "freshly indexed"
        lines.append(
            f"Indexed **{rag.indexed_files}** repository document(s) into **{rag.chunks_indexed}** chunk(s) "
            f"from branch `{rag.default_branch}` ({cache_label})."
        )
        lines.append("")
        if rag.indexed_doc_paths:
            lines.append("**Documents retrieved:**")
            for path in rag.indexed_doc_paths:
                lines.append(f"- `{path}`")
            lines.append("")
        if rag.retrieved:
            lines.append("**Top repository context retrieved:**")
            lines.append("")
            for chunk in rag.retrieved[:5]:
                lines.append(f"#### `{chunk.path}`")
                if chunk.retrieval_reason:
                    lines.append(f"**Why retrieved:** {chunk.retrieval_reason}")
                lines.append(f"```")
                lines.append(f"{chunk.snippet[:300]}{'...' if len(chunk.snippet) > 300 else ''}")
                lines.append(f"```")
                lines.append("")
        else:
            lines.append("No chunk was similar enough to the diff to be surfaced as supporting context.")
            lines.append("")
    else:
        lines.append(f"Repository context was not retrieved for this run ({rag.skip_reason or 'not available'}).")
        lines.append("")

    # --- Deployment Recommendation ------------------------------------------------
    rec = report.deployment_recommendation
    lines.extend(["## Deployment Recommendation", ""])
    if rec:
        lines.append(f"**Chosen strategy: `{rec.strategy}`**")
        lines.append("")
        lines.append(rec.reason or ai.rollout_reason)
        lines.append("")
        if rec.monitoring_focus:
            lines.append(f"- **Monitoring focus:** {rec.monitoring_focus}")
        if rec.rollback_trigger:
            lines.append(f"- **Rollback trigger:** {rec.rollback_trigger}")
        if rec.approval_level:
            lines.append(f"- **Required approval:** `{rec.approval_level}`")
        lines.append(f"- **Rollback plan required:** {'Yes' if rec.rollback_required else 'No'}")
        lines.append("")
        if rec.alternatives_considered:
            lines.append("**Alternatives considered:**")
            for alt in rec.alternatives_considered:
                lines.append(f"- {alt}")
            lines.append("")

    # --- Confidence explanation ------------------------------------------------
    conf = report.confidence_explanation
    if conf:
        lines.extend(["## Confidence", ""])
        lines.append(f"**{conf.level}** ({conf.score}% score) — {conf.evidence_completeness} evidence")
        lines.append("")
        lines.append(conf.narrative)
        lines.append("")
        lines.append(f"- Repository context available: {'Yes' if conf.repository_context_available else 'No'}")
        lines.append(f"- LLM and heuristic analyses agree: {'Yes' if conf.llm_heuristic_agreement else 'No'}")
        lines.append("")

    if report.high_risk_files:
        lines.extend(["## Changed High-Risk Files", ""])
        for f in report.high_risk_files:
            lines.append(f"- `{f}`")
        lines.append("")

    if report.timeline:
        lines.extend(["## Execution Metrics", ""])
        total = metrics.total_duration_ms if metrics else sum(t.duration_ms for t in report.timeline)
        lines.append(f"- **Total duration:** {_format_duration(total)}")
        for stage in report.timeline:
            lines.append(f"- {stage.stage}: {_format_duration(stage.duration_ms)}")
        lines.append("")

    if response.judge:
        lines.extend([
            "## Groundedness Check",
            "",
            f"**Verdict:** {'Grounded' if response.judge.grounded else 'Issues detected'}",
        ])
        if response.judge.issues:
            for issue in response.judge.issues:
                lines.append(f"- {issue}")
        if response.judge.notes:
            lines.append(f"- _{response.judge.notes}_")
        lines.append("")

    if not response.ai_enabled:
        lines.extend([
            "> ⚠️ **Note:** AI analysis unavailable — this report reflects deterministic heuristics only.",
            f"> {response.ai_error or 'Ollama unavailable'}",
            "",
        ])

    lines.append("---")
    lines.append("*Generated by [PR Sentinel](https://github.com) — AI-powered deployment risk analysis.*")

    return "\n".join(lines)


def render_comment(response: AnalyzeResponse) -> str:
    """Shorter Markdown suitable for GitHub PR comments."""
    return render_markdown(response)


# ANSI color codes for terminal output
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_BLUE = "\033[94m"
_CYAN = "\033[96m"
_MAGENTA = "\033[95m"


def _color(text: str, code: str) -> str:
    return f"{code}{text}{_RESET}"


def _risk_color(level: RiskLevel | str) -> str:
    label = _risk_label(level)
    if label == "HIGH":
        return _RED
    if label == "MEDIUM":
        return _YELLOW
    return _GREEN


def render_console(response: AnalyzeResponse) -> str:
    """Colored terminal summary for CLI output."""
    pr = response.pr
    report = response.report
    ai = response.ai
    lines: list[str] = []

    lines.append("")
    lines.append(_color("═" * 60, _DIM))
    lines.append(_color("  PR SENTINEL — Deployment Risk Analysis", _BOLD + _CYAN))
    lines.append(_color("═" * 60, _DIM))
    lines.append("")

    repo_str = f"{pr.owner}/{pr.repo}#{pr.number}"
    lines.append(f"  {_color('Repository:', _DIM)} {repo_str}")
    lines.append(f"  {_color('Title:', _DIM)} {pr.title[:70]}")
    lines.append("")

    decision_color = _RED if report.decision == "BLOCK" else _GREEN
    risk_color = _risk_color(ai.overall_risk)
    lines.append(f"  {_color('Decision:', _BOLD)} {_color(report.decision, decision_color + _BOLD)}")
    lines.append(
        f"  {_color('Overall Risk:', _BOLD)} {_color(_risk_label(ai.overall_risk), risk_color + _BOLD)}"
    )
    lines.append(f"  {_color('Risk Score:', _DIM)} {report.risk_score}/100")
    lines.append(f"  {_color('Confidence:', _DIM)} {report.confidence}%")
    lines.append("")

    lines.append(_color("  Risk Breakdown", _BOLD))
    lines.append(_color("  " + "─" * 40, _DIM))
    for cat in report.risk_categories or []:
        cat_color = _risk_color(cat.status)
        lines.append(
            f"  {_color(cat.category + ':', _DIM)} "
            f"{_color(_risk_label(cat.status), cat_color)} "
            f"({cat.score})"
        )
        for reason in cat.reasons[:2]:
            lines.append(f"    {_color('›', _DIM)} {reason}")
    lines.append("")

    lines.append(_color("  Deployment Recommendation", _BOLD))
    lines.append(_color("  " + "─" * 40, _DIM))
    lines.append(f"  {_color(ai.rollout_strategy, _MAGENTA + _BOLD)}")
    lines.append(f"  {ai.rollout_reason[:120]}")
    lines.append("")

    if report.agent_statuses:
        lines.append(_color("  Agent Pipeline", _BOLD))
        lines.append(_color("  " + "─" * 40, _DIM))
        for status in report.agent_statuses:
            status_color = {
                "Completed": _GREEN,
                "Skipped": _DIM,
                "Failed": _RED,
                "Running": _YELLOW,
            }.get(status.status, _DIM)
            dur = f" ({_format_duration(status.duration_ms)})" if status.duration_ms else ""
            lines.append(
                f"  {_color('●', status_color)} {status.label}: "
                f"{_color(status.status, status_color)}{dur}"
            )
        lines.append("")

    rag = response.rag
    if rag.scanned:
        cache_msg = "cache hit" if rag.cache_hit else "indexed"
        lines.append(
            f"  {_color('RAG:', _DIM)} Repository context {cache_msg} "
            f"({rag.indexed_files} docs, {rag.chunks_indexed} chunks)"
        )
        lines.append("")

    if report.high_risk_files:
        lines.append(_color("  High-Risk Files", _BOLD))
        for f in report.high_risk_files[:5]:
            lines.append(f"  {_color('!', _RED)} {f}")
        lines.append("")

    metrics = report.execution_metrics
    if metrics:
        lines.append(
            f"  {_color('Duration:', _DIM)} {_format_duration(metrics.total_duration_ms)} "
            f"{_color('|', _DIM)} {_color('Generated:', _DIM)} {_format_timestamp(metrics.generated_at)}"
        )
        lines.append("")

    if report.decision == "BLOCK":
        lines.append(_color("  ✗ Analysis complete — BLOCK recommended", _RED + _BOLD))
    else:
        lines.append(_color("  ✓ Analysis complete — ALLOW recommended", _GREEN + _BOLD))
    lines.append("")

    return "\n".join(lines)
