from __future__ import annotations

from datetime import datetime, timezone

from .models import AnalyzeResponse, RiskLevel


def _risk_label(level: RiskLevel | str) -> str:
    if isinstance(level, RiskLevel):
        return level.value
    return str(level)


def _decision_emoji(decision: str) -> str:
    return "🚫" if decision == "BLOCK" else "✅"


def render_markdown(response: AnalyzeResponse) -> str:
    """Generate a professional Markdown report suitable for GitHub PR comments and artifacts."""
    pr = response.pr
    report = response.report
    ai = response.ai
    rag = response.rag
    metrics = report.execution_metrics
    generated = metrics.generated_at if metrics else datetime.now(timezone.utc).isoformat()

    lines: list[str] = [
        "# PR Sentinel — Deployment Risk Report",
        "",
        f"**Generated:** {generated}",
        "",
        "## Summary",
        "",
        report.summary or ai.summary,
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| **Decision** | `{report.decision}` |",
        f"| **Overall Risk** | `{_risk_label(ai.overall_risk)}` |",
        f"| **Risk Score** | {report.risk_score} / 100 |",
        f"| **Confidence** | {report.confidence}% |",
        f"| **Deployment** | {report.deployment_strategy} |",
        "",
        "## Repository",
        "",
        f"- **Repository:** [{pr.repository.full_name}]({pr.url})",
        f"- **PR:** #{pr.number} — {pr.title}",
        f"- **Author:** @{pr.author}",
        f"- **Branch:** `{pr.head_branch or 'unknown'}` → `{pr.base_branch or report.repository_intelligence.default_branch or 'main'}`",
        f"- **Language:** {report.repository_intelligence.primary_language or pr.repository.primary_language or 'Unknown'}",
        f"- **Framework:** {report.repository_intelligence.framework or pr.repository.framework or 'Unknown'}",
        f"- **Stars:** {pr.repository.stars:,}",
        f"- **Files Changed:** {pr.changed_files_count} (+{pr.additions}/-{pr.deletions})",
        f"- **Commits:** {len(pr.commit_messages)}",
        f"- **Merge Status:** {pr.mergeable_state or 'unknown'}",
        "",
    ]

    intel = report.repository_intelligence
    if intel.containerization or intel.ci_provider or intel.infrastructure:
        lines.extend(["## Repository Intelligence", ""])
        if intel.containerization:
            lines.append(f"- **Containerization:** {intel.containerization}")
        if intel.ci_provider:
            lines.append(f"- **CI Provider:** {intel.ci_provider}")
        if intel.infrastructure:
            lines.append(f"- **Infrastructure:** {', '.join(intel.infrastructure)}")
        lines.append(f"- **Estimated Size:** {intel.estimated_size}")
        lines.append(f"- **Default Branch:** `{intel.default_branch or 'main'}`")
        lines.append("")

    if report.risk_categories:
        lines.extend(["## Risk Breakdown", ""])
        for cat in report.risk_categories:
            lines.append(f"### {cat.category} — `{_risk_label(cat.status)}` (score: {cat.score})")
            for reason in cat.reasons:
                lines.append(f"- {reason}")
            if cat.evidence_files:
                files = ", ".join(f"`{f}`" for f in cat.evidence_files[:5])
                lines.append(f"- **Evidence files:** {files}")
            lines.append("")

    if report.evidence_items:
        lines.extend(["## Evidence", ""])
        for item in report.evidence_items:
            lines.append(f"### {item.category}")
            if item.files:
                lines.append(f"**Detected from:** {', '.join(f'`{f}`' for f in item.files)}")
            lines.append(f"**Reason:** {item.reason}")
            lines.append("")

    if report.high_risk_files:
        lines.extend(["## Changed High-Risk Files", ""])
        for f in report.high_risk_files:
            lines.append(f"- `{f}`")
        lines.append("")

    lines.extend([
        "## Deployment Recommendation",
        "",
        f"**Strategy:** {ai.rollout_strategy}",
        "",
        f"**Reason:** {ai.rollout_reason}",
        "",
        f"**Confidence:** {ai.confidence}%",
        "",
        f"**Rollback Required:** {'Yes' if ai.rollback_required else 'No'}",
        "",
    ])

    if report.agent_statuses:
        lines.extend(["## Agent Pipeline", ""])
        lines.append("| Agent | Status | Files | Duration |")
        lines.append("|-------|--------|-------|----------|")
        for status in report.agent_statuses:
            dur = f"{status.duration_ms}ms" if status.duration_ms else "—"
            lines.append(
                f"| {status.label} | {status.status} | {status.files_reviewed} | {dur} |"
            )
        lines.append("")

    if rag.scanned:
        cache_label = "Repository context cache hit" if rag.cache_hit else "Repository indexed"
        lines.extend([
            "## Repository Context (RAG)",
            "",
            f"**Status:** {cache_label}",
            f"**Branch:** `{rag.default_branch}`",
            f"**Indexed documents:** {rag.indexed_files} file(s), {rag.chunks_indexed} chunk(s)",
            "",
        ])
        if rag.indexed_doc_paths:
            lines.append("**Documents retrieved:**")
            for path in rag.indexed_doc_paths:
                lines.append(f"- `{path}`")
            lines.append("")
        if rag.retrieved:
            lines.append("**Top retrieved chunks:**")
            for chunk in rag.retrieved[:5]:
                lines.append(f"- `[{chunk.path}]` (score: {chunk.score:.2f})")
                lines.append(f"  > {chunk.snippet[:200]}...")
            lines.append("")

    if report.timeline:
        lines.extend(["## Execution Metrics", ""])
        total = metrics.total_duration_ms if metrics else sum(t.duration_ms for t in report.timeline)
        lines.append(f"- **Total duration:** {total:,}ms")
        for stage in report.timeline:
            lines.append(f"- {stage.stage}: {stage.duration_ms:,}ms")
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
            "> ⚠️ **Note:** AI analysis unavailable — report based on deterministic heuristics only.",
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
            dur = f" ({status.duration_ms}ms)" if status.duration_ms else ""
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
            f"  {_color('Duration:', _DIM)} {metrics.total_duration_ms:,}ms "
            f"{_color('|', _DIM)} {_color('Generated:', _DIM)} {metrics.generated_at[:19]}"
        )
        lines.append("")

    if report.decision == "BLOCK":
        lines.append(_color("  ✗ Analysis complete — BLOCK recommended", _RED + _BOLD))
    else:
        lines.append(_color("  ✓ Analysis complete — ALLOW recommended", _GREEN + _BOLD))
    lines.append("")

    return "\n".join(lines)
