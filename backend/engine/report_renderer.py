from __future__ import annotations

from datetime import datetime, timezone

from .models import AnalyzeResponse, RiskLevel


def _risk_label(level: RiskLevel | str) -> str:
    if isinstance(level, RiskLevel):
        return level.value
    return str(level)


def _decision_emoji(decision: str) -> str:
    if decision == "BLOCK":
        return "🚫"
    if decision == "NEEDS_REVIEW":
        return "⚠️"
    return "✅"


def _format_timestamp(raw: str) -> str:
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        return f"{dt.strftime('%b %-d, %Y, %H:%M')} UTC"
    except (ValueError, TypeError):
        return raw[:19].replace("T", " ") + " UTC" if len(raw) >= 19 else raw


def _format_duration(ms: int | float) -> str:
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


def _decision_bullets(response: AnalyzeResponse) -> list[str]:
    report = response.report
    heuristics = response.heuristics
    bullets: list[str] = []

    triggered = [f for f in heuristics.factors if f.triggered]
    for factor in triggered[:3]:
        bullets.append(f"**{factor.label}** — {factor.reason}")

    if report.review_complexity and report.review_complexity.level == RiskLevel.HIGH and not triggered:
        bullets.append(
            f"**Review Complexity {report.review_complexity.level.value}** — "
            + "; ".join(report.review_complexity.drivers[:2])
        )

    if report.llm_disagreement and report.llm_disagreement.detected:
        bullets.append(
            f"**Deterministic override** — LLM assessed {_risk_label(report.llm_disagreement.llm_risk)}; "
            f"policy classified {_risk_label(report.llm_disagreement.deterministic_risk)}."
        )

    if not bullets:
        bullets.append("No security, migration, infrastructure, or test-removal signals detected.")

    return bullets[:5]


def render_markdown(response: AnalyzeResponse) -> str:
    """Three-tier Markdown report: 5-second decision, 30-second action, detailed evidence."""
    pr = response.pr
    report = response.report
    ai = response.ai
    rag = response.rag
    metrics = report.execution_metrics
    generated_raw = metrics.generated_at if metrics else datetime.now(timezone.utc).isoformat()
    generated = _format_timestamp(generated_raw)

    release_risk = report.release_risk or ai.overall_risk
    complexity = report.review_complexity
    evidence_tier = report.confidence_explanation.level if report.confidence_explanation else "MEDIUM"
    readiness = report.production_readiness
    readiness_score = readiness.score if readiness else max(0, 100 - report.risk_score)

    main_concern = _decision_bullets(response)[0].split("—")[0].replace("*", "").strip()
    if complexity and complexity.level == RiskLevel.HIGH and release_risk == RiskLevel.LOW:
        main_concern = "Large change surface requires focused review"

    lines: list[str] = [
        "# PR Sentinel",
        "",
        "────────────────────────────",
        "",
        f"## {_decision_emoji(report.decision)} {report.decision}",
        "",
        f"| **Release Risk** | `{_risk_label(release_risk)}` |",
        f"| **Review Complexity** | `{_risk_label(complexity.level) if complexity else 'MEDIUM'}` |",
        f"| **Merge Readiness** | {readiness_score}/100 |",
        f"| **Evidence Confidence** | {evidence_tier} |",
        "",
        f"**Main concern:** {main_concern}",
        "",
        "**Why:** "
        + (
            "No security, migration, infrastructure, or test-removal signals detected."
            if release_risk == RiskLevel.LOW and not [f for f in response.heuristics.factors if f.triggered]
            else "; ".join(b.split("—")[-1].strip() for b in _decision_bullets(response)[:2])
        ),
        "",
    ]

    if response.policy_note or not response.ai_enabled:
        lines.extend([
            f"> {response.policy_note or 'AI synthesis unavailable. Final release decision was produced by the deterministic policy engine.'}",
            "",
        ])

    if response.judge and response.judge.grounded is False:
        lines.extend([
            "> ⚠ **Evidence requires review** — the groundedness check flagged claims in "
            "this report that aren't fully supported by the underlying evidence. The "
            "release decision above is unaffected (it's produced by deterministic "
            "policy, not the LLM narrative), but read the executive summary and agent "
            "findings with that in mind.",
            "",
        ])

    if report.llm_disagreement and report.llm_disagreement.detected:
        lines.extend([
            "### ⚠ Deterministic Override",
            "",
            f"- **LLM assessment:** `{_risk_label(report.llm_disagreement.llm_risk)}`",
            f"- **Deterministic assessment:** `{_risk_label(report.llm_disagreement.deterministic_risk)}`",
            f"- **Final decision:** `{report.decision}`",
            "",
        ])

    # --- Tier 2: 30-second view ------------------------------------------------
    lines.extend(["## Why this decision?", ""])
    for bullet in _decision_bullets(response):
        lines.append(f"- {bullet}")
    lines.append("")

    if report.review_queue:
        lines.extend(["## Review Queue", ""])
        for item in report.review_queue[:5]:
            lines.append(
                f"- **{item.priority}** `{item.filename}` — {item.role}. "
                f"_{item.why_it_matters}_ (~{item.estimated_minutes} min)"
            )
        lines.append("")

    if report.operational_checklist:
        lines.extend(["## Merge Checklist", ""])
        for item in report.operational_checklist[:6]:
            lines.append(f"- [ ] {item.task} — _{item.reason}_")
        lines.append("")

    # --- Tier 3: Detailed evidence ---------------------------------------------
    lines.extend([
        "---",
        "",
        "## Detailed Evidence",
        "",
        f"**Summary:** {report.executive_summary or report.summary or ai.summary}",
        "",
    ])

    if report.score_math:
        lines.extend(["### Release Risk Calculation", ""])
        lines.append("| Factor | Points | Evidence |")
        lines.append("|---|---|---|")
        for item in report.score_math:
            pts = f"+{item.points}" if item.points > 0 else f"{item.points}"
            lines.append(f"| {item.factor} | `{pts}` | {item.reason} |")
        lines.append(f"| **Release Risk Score** | **`{report.risk_score}`** | → `{_risk_label(release_risk)}` → `{report.decision}` |")
        lines.append("")

    if complexity:
        lines.extend(["### Review Complexity Calculation", ""])
        lines.append(f"**Level:** `{_risk_label(complexity.level)}` (score {complexity.score}/100)")
        lines.append("")
        lines.append("**Drivers:**")
        for driver in complexity.drivers:
            lines.append(f"- {driver}")
        lines.append("")

    if report.llm_disagreement:
        d = report.llm_disagreement
        lines.extend([
            "### LLM Disagreement Audit",
            "",
            f"- Detected: **{'yes' if d.detected else 'no'}**",
            f"- Deterministic release risk: `{_risk_label(d.deterministic_risk)}`",
            f"- LLM assessment: `{_risk_label(d.llm_risk) if d.llm_risk else 'n/a'}`",
            f"- Final release risk: `{_risk_label(d.final_risk)}`",
            f"- Reason: {d.reason}",
            "",
        ])

    if report.specialist_routing:
        lines.extend(["### Specialist Routing", ""])
        lines.append("| Specialist | Status | Trigger | Files | Duration |")
        lines.append("|---|---|---|---|---|")
        for entry in report.specialist_routing:
            dur = _format_duration(entry.duration_ms) if entry.duration_ms else "—"
            llm = "yes" if entry.llm_call_made else "no"
            lines.append(
                f"| {entry.label} | **{entry.status}** | {entry.trigger} | {entry.files_count} | {dur} (LLM: {llm}) |"
            )
        lines.append("")

    if report.agent_decisions:
        lines.extend(["### Agent Findings", ""])
        for d in report.agent_decisions:
            if d.decision.startswith("SKIPPED"):
                continue
            lines.append(f"- **{d.label}:** {d.decision} — {d.reasoning[:200]}")
        lines.append("")

    if rag.scanned and rag.retrieved:
        lines.extend(["### Repository Context (RAG)", ""])
        for chunk in rag.retrieved[:3]:
            lines.append(f"- `{chunk.path}`: {chunk.snippet[:200]}...")
        lines.append("")

    if response.judge:
        grounded = response.judge.grounded
        lines.extend([
            "### Groundedness Check",
            "",
            f"**Evidence Quality:** {'HIGH' if grounded else 'REVIEW'}",
            f"**Groundedness:** {'PASSED' if grounded else 'FAILED'}",
            "",
            "The release decision remains governed by deterministic policy.",
            "",
        ])
        if response.judge.issues:
            for issue in response.judge.issues:
                lines.append(f"- {issue}")
            lines.append("")

    if report.engineering_metrics:
        em = report.engineering_metrics
        lines.extend([
            "### Engineering Metrics",
            "",
            f"- Lines: +{em.lines_added}/-{em.lines_removed} across {pr.changed_files_count} files",
            f"- Test files touched: {em.test_files_touched}",
            f"- Hotspot: `{em.largest_file}` ({em.hotspot_concentration_pct}% of diff)",
            "",
        ])

    if metrics:
        lines.extend([
            "### Execution Diagnostics",
            "",
            f"- Total duration: {_format_duration(metrics.total_duration_ms)}",
            f"- AI enabled: {metrics.ai_enabled}",
            f"- RAG cache hit: {metrics.rag_cache_hit}",
            "",
        ])

    lines.append("---")
    lines.append("*Generated by PR Sentinel — deterministic policy controls release decisions; LLM agents explain evidence.*")

    return "\n".join(lines)


def render_comment(response: AnalyzeResponse) -> str:
    return render_markdown(response)


_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
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
    pr = response.pr
    report = response.report
    release_risk = report.release_risk
    lines: list[str] = []

    lines.append("")
    lines.append(_color("═" * 60, _DIM))
    lines.append(_color("  PR SENTINEL — Release Risk Assessment", _BOLD + _CYAN))
    lines.append(_color("═" * 60, _DIM))
    lines.append("")
    lines.append(f"  {_color('Repository:', _DIM)} {pr.owner}/{pr.repo}#{pr.number}")
    lines.append(f"  {_color('Title:', _DIM)} {pr.title[:70]}")
    lines.append("")

    decision_color = _RED if report.decision == "BLOCK" else (_YELLOW if report.decision == "NEEDS_REVIEW" else _GREEN)
    risk_color = _risk_color(release_risk)
    lines.append(f"  {_color('Decision:', _BOLD)} {_color(report.decision, decision_color + _BOLD)}")
    lines.append(f"  {_color('Release Risk:', _BOLD)} {_color(_risk_label(release_risk), risk_color + _BOLD)}")
    if report.review_complexity:
        lines.append(
            f"  {_color('Review Complexity:', _DIM)} {_risk_label(report.review_complexity.level)}"
        )
    lines.append(f"  {_color('Risk Score:', _DIM)} {report.risk_score}/100")
    if report.confidence_explanation:
        lines.append(f"  {_color('Evidence Confidence:', _DIM)} {report.confidence_explanation.level}")
    lines.append("")

    if report.llm_disagreement and report.llm_disagreement.detected:
        lines.append(_color("  ⚠ Deterministic Override — LLM cannot change release policy", _YELLOW))
        lines.append("")

    if response.judge and response.judge.grounded is False:
        lines.append(_color("  ⚠ Evidence requires review — groundedness check flagged unsupported claims", _YELLOW))
        lines.append("")

    if not response.ai_enabled:
        lines.append(_color("  AI synthesis unavailable — deterministic policy authoritative", _YELLOW))
        lines.append("")

    metrics = report.execution_metrics
    if metrics:
        lines.append(
            f"  {_color('Duration:', _DIM)} {_format_duration(metrics.total_duration_ms)}"
        )
        lines.append("")

    return "\n".join(lines)
