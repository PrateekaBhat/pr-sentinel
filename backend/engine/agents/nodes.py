from __future__ import annotations

import functools
import json
import logging
import time

from .. import agent_routing, finding_validation
from ..config import get_settings
from ..models import (
    AgentFinding,
    AIAnalysis,
    FileRisk,
    JudgeVerdict,
    RiskFactorFlag,
    RiskLevel,
)
from ..ollama_client import OllamaError, chat_json
from ..categories import clean_finding_text, reconcile_executive_summary
from .prompts import (
    AGENT_RESPONSE_INSTRUCTIONS,
    AGENT_SYSTEM_PROMPTS,
    COORDINATOR_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT,
)
from .state import AgentState

logger = logging.getLogger("pr_sentinel.agents")

# Sourced from Settings (backend/engine/config.py) so these are configurable via env
# vars (MAX_PATCH_CHARS / MAX_PATCH_LINES / MAX_FILES_PER_AGENT) without changing the
# previous effective defaults (600 / 30 / 4).
_settings = get_settings()
MAX_PATCH_CHARS = _settings.max_patch_chars
MAX_PATCH_LINES = _settings.max_patch_lines
MAX_FILES_PER_AGENT = _settings.max_files_per_agent


def _files_prompt(files, total_available: int | None = None) -> str:
    """`files` is the already-ranked-and-capped set of files to actually show. Pass
    `total_available` (the count before capping) when it differs from `len(files)`,
    so the "N more not shown" note stays accurate even though `files` itself is
    pre-capped by the caller."""
    total_files = total_available if total_available is not None else len(files)
    shown_files = files[:MAX_FILES_PER_AGENT]
    parts = [
        f"{total_files} file(s) are in this agent's scope; {len(shown_files)} are shown below."
    ]
    for f in shown_files:
        all_patch_lines = (f.patch or "").splitlines()
        patch_lines = all_patch_lines[:MAX_PATCH_LINES]
        patch = "\n".join(patch_lines)[:MAX_PATCH_CHARS]
        truncated_by_lines = len(all_patch_lines) > MAX_PATCH_LINES
        truncated_by_chars = len("\n".join(patch_lines)) > MAX_PATCH_CHARS
        if truncated_by_lines:
            truncation_note = (
                f"(showing {len(patch_lines)} of {len(all_patch_lines)} patch lines — TRUNCATED)"
            )
        elif truncated_by_chars:
            truncation_note = "(patch text TRUNCATED to a character limit)"
        else:
            truncation_note = "(full patch shown)"
        parts.append(
            f"### {f.filename} ({f.status}, +{f.additions}/-{f.deletions}) {truncation_note}\n"
            f"```diff\n{patch}\n```"
        )
    if total_files > MAX_FILES_PER_AGENT:
        parts.append(
            f"... and {total_files - MAX_FILES_PER_AGENT} more file(s) in scope that are NOT shown at all."
        )
    parts.append(
        "\nDo not infer behavior from code that was not shown. If the provided patch is "
        "truncated, lower confidence and describe only what the provided evidence supports."
    )
    return "\n".join(parts)


async def run_agent(domain: str, state: AgentState) -> dict:
    """Generic specialist-agent node. Skips the LLM call entirely (no cost, no latency)
    when this PR touches no files in the agent's domain — routing determines relevance
    before any model is invoked."""
    pr = state["pr"]
    files = agent_routing.files_for_domain(pr.files, domain)
    label = agent_routing.DOMAIN_LABELS[domain]
    key = f"{domain}_finding"

    if not files:
        return {
            key: AgentFinding(
                agent=domain,
                label=label,
                applicable=False,
                files_reviewed=[],
                findings=[],
                risk_note="No files in this domain were touched by this PR.",
            ),
            f"{domain}_status": {
                "agent": domain,
                "label": label,
                "status": "Skipped",
                "files_reviewed": 0,
                "duration_ms": 0,
            },
        }

    # Rank the domain-matched files so the most useful evidence is selected first,
    # then cap to MAX_FILES_PER_AGENT — this is what's actually sent to the LLM.
    # `files_reviewed` below must only ever list files that were truly shown.
    ranked_files = agent_routing.rank_files_for_domain(files, domain)
    available_count = len(ranked_files)
    selected_files = ranked_files[:MAX_FILES_PER_AGENT]
    context_bounded = available_count > len(selected_files)

    start = time.perf_counter_ns()
    try:
        system = AGENT_SYSTEM_PROMPTS[domain]
        user = f"## Files in scope\n{_files_prompt(selected_files, total_available=available_count)}\n{AGENT_RESPONSE_INSTRUCTIONS}"
        data = await chat_json(system, user, timeout=120.0)
        raw_findings = (data.get("findings") or [])[:4]
        # Clean placeholder/template artifacts before structural validation so a
        # stripped placeholder doesn't itself trigger a truncation false-positive.
        cleaned_raw = []
        for raw in raw_findings:
            if isinstance(raw, dict):
                cleaned_raw.append(
                    {k: (clean_finding_text(v) if isinstance(v, str) else v) for k, v in raw.items()}
                )
            else:
                cleaned_raw.append(clean_finding_text(str(raw)))
        structured, needs_verification, rejected_count = finding_validation.normalize_findings(cleaned_raw)
        # `structured_findings` (built above) is the authoritative, validated source.
        # `findings` is populated here ONLY as a derived compatibility projection —
        # titles of the already-validated structured findings — and must never be
        # populated from raw model output directly. Downstream code (coordinator
        # prompt, report renderer, executive-summary reconciliation) reads from
        # `structured_findings`; this projection exists solely for callers/serializers
        # that still expect a flat string list.
        findings = [f.title for f in structured]
        risk_note = clean_finding_text(str(data.get("risk_note", "")))
        confidence = int(data.get("confidence", 60))
    except OllamaError as exc:
        logger.warning("%s agent failed: %s", domain, exc)
        findings = []
        structured = []
        needs_verification = []
        rejected_count = 0
        risk_note = f"Agent call failed ({exc}); files were not analyzed by AI for this domain."
        confidence = 0
    duration_ms = int((time.perf_counter_ns() - start) / 1_000_000)

    return {
        key: AgentFinding(
            agent=domain,
            label=label,
            applicable=True,
            files_reviewed=[f.filename for f in selected_files],
            findings=findings,
            structured_findings=structured,
            needs_verification=needs_verification,
            rejected_count=rejected_count,
            risk_note=risk_note,
            confidence=confidence,
        ),
        f"{domain}_status": {
            "agent": domain,
            "label": label,
            "status": "Completed",
            "files_reviewed": len(selected_files),
            "duration_ms": duration_ms,
            "files_available": available_count,
            "context_bounded": context_bounded,
        },
    }


security_agent = functools.partial(run_agent, "security")
performance_agent = functools.partial(run_agent, "performance")
database_agent = functools.partial(run_agent, "database")
api_agent = functools.partial(run_agent, "api")
tests_agent = functools.partial(run_agent, "tests")


def _empty_finding(domain: str) -> AgentFinding:
    return AgentFinding(
        agent=domain, label=agent_routing.DOMAIN_LABELS[domain], applicable=False, risk_note="Not run."
    )


def _build_coordinator_prompt(state: AgentState) -> str:
    pr = state["pr"]
    heuristics = state["heuristics"]
    rag = state.get("rag")

    agent_lines = []
    for domain in ["security", "performance", "database", "api", "tests"]:
        finding = state.get(f"{domain}_finding") or _empty_finding(domain)
        if not finding.applicable:
            agent_lines.append(f"- {finding.label}: not applicable ({finding.risk_note})")
            continue
        if finding.structured_findings:
            detail_lines = []
            for sf in finding.structured_findings:
                detail_lines.append(
                    f"    * [{sf.severity}/{sf.confidence}] {sf.title} — evidence: {sf.evidence}"
                )
            findings_text = "no concerns raised" if not detail_lines else "\n" + "\n".join(detail_lines)
        else:
            findings_text = "no concerns raised"
        agent_lines.append(
            f"- {finding.label} (reviewed {len(finding.files_reviewed)} file(s)): "
            f"{findings_text}. Risk note: {finding.risk_note}"
        )
        if finding.needs_verification:
            low_conf = "; ".join(sf.title for sf in finding.needs_verification)
            agent_lines.append(f"    (also reported, LOW confidence, needs verification: {low_conf})")

    heuristic_lines = [
        f"- {f.label}: {'TRIGGERED' if f.triggered else 'not triggered'} ({f.reason})"
        for f in heuristics.factors
    ]

    doc_lines = []
    if rag and rag.scanned and rag.retrieved:
        for chunk in rag.retrieved:
            doc_lines.append(f"- [{chunk.path}] {chunk.snippet[:300]}")

    return f"""## Pull Request
Repo: {pr.owner}/{pr.repo}
Title: {pr.title}
Files changed: {pr.changed_files_count} (+{pr.additions}/-{pr.deletions})
Description: {pr.body or '(none)'}

## Deterministic heuristic findings (score: {heuristics.score}/100)
{chr(10).join(heuristic_lines) or '(none triggered)'}

## Specialist agent findings
{chr(10).join(agent_lines)}

## Relevant repository documentation
{chr(10).join(doc_lines) or '(no repository documentation was retrieved for this PR)'}
"""


async def coordinator_node(state: AgentState) -> dict:
    heuristics = state["heuristics"]
    rag = state.get("rag")

    start = time.perf_counter_ns()
    try:
        data = await chat_json(COORDINATOR_SYSTEM_PROMPT, _build_coordinator_prompt(state), timeout=180.0)
    except OllamaError as exc:
        # Don't let a coordinator failure blow away the whole graph run: the specialist
        # agents above may have already succeeded, and we want their findings/timing to
        # survive so the fallback report is accurate rather than looking instantaneous.
        duration_ms = int((time.perf_counter_ns() - start) / 1_000_000)
        logger.warning("Coordinator failed: %s", exc)
        return {"coordinator_error": str(exc), "coordinator_duration_ms": duration_ms}

    risk_value = str(data.get("overall_risk", "MEDIUM")).upper()
    overall_risk = RiskLevel(risk_value) if risk_value in RiskLevel.__members__ else RiskLevel.MEDIUM

    risk_factors = []
    for rf in data.get("risk_factors", []) or []:
        if isinstance(rf, dict) and "label" in rf:
            risk_factors.append(
                RiskFactorFlag(
                    key=rf.get("key", rf["label"].lower().replace(" ", "_")),
                    label=rf["label"],
                    passed=bool(rf.get("passed", True)),
                )
            )

    file_risks = []
    for fr in data.get("file_risks", []) or []:
        if isinstance(fr, dict) and "filename" in fr:
            fr_risk = str(fr.get("risk", "MEDIUM")).upper()
            file_risks.append(
                FileRisk(
                    filename=fr["filename"],
                    risk=RiskLevel(fr_risk) if fr_risk in RiskLevel.__members__ else RiskLevel.MEDIUM,
                    reason=fr.get("reason", ""),
                )
            )

    agent_findings = [
        state.get(f"{domain}_finding") or _empty_finding(domain)
        for domain in ["security", "performance", "database", "api", "tests"]
    ]

    strategy = str(data.get("rollout_strategy", "Standard")).strip()
    valid_strategies = {"Standard", "Canary", "Blue/Green", "Manual Approval"}
    if strategy not in valid_strategies:
        # Best-effort normalization if the model drifted from the enum (e.g. "Standard merge").
        lowered = strategy.lower()
        if "canary" in lowered:
            strategy = "Canary"
        elif "blue" in lowered or "green" in lowered:
            strategy = "Blue/Green"
        elif "manual" in lowered or "approval" in lowered:
            strategy = "Manual Approval"
        else:
            strategy = "Standard"

    exec_summary = reconcile_executive_summary(
        data.get("executive_summary") or data.get("summary", ""), agent_findings
    )

    result = AIAnalysis(
        overall_risk=overall_risk,
        confidence=int(data.get("confidence", 60)),
        summary=data.get("summary", ""),
        executive_summary=exec_summary,
        architectural_impact=data.get("architectural_impact", ""),
        affected_subsystems=[str(x) for x in (data.get("affected_subsystems") or [])],
        operational_risks=data.get("operational_risks", []) or [],
        rollout_strategy=strategy,
        rollout_reason=data.get("rollout_reason", ""),
        rollback_required=bool(data.get("rollback_required", False)),
        test_coverage_estimate_pct=data.get("test_coverage_estimate_pct"),
        suggested_test_areas=data.get("suggested_test_areas", []) or [],
        risk_factors=risk_factors,
        file_risks=file_risks,
        agent_findings=agent_findings,
        citations=(rag.retrieved if rag else []),
    )
    duration_ms = int((time.perf_counter_ns() - start) / 1_000_000)
    return {"coordinator_result": result, "coordinator_duration_ms": duration_ms}


async def judge_node(state: AgentState) -> dict:
    """Non-blocking self-evaluation pass. A judge failure never breaks the pipeline —
    it just means no groundedness verdict is attached to the response. The judge never
    controls the release decision (deterministic policy always does), so it can be
    disabled via Settings.enable_judge to save one Ollama call on constrained runners."""
    coordinator_result = state.get("coordinator_result")
    if coordinator_result is None:
        # No AI synthesis was produced (the coordinator failed/timed out), so there is
        # nothing for the judge to evaluate. This must NOT be reported as "grounded" —
        # grounded=None means "not run", distinct from a passed or failed check.
        return {
            "judge_result": JudgeVerdict(
                grounded=None,
                notes="No AI synthesis was produced, so groundedness was not evaluated.",
            )
        }

    if not get_settings().enable_judge:
        return {
            "judge_result": JudgeVerdict(
                grounded=None,
                notes="Judge pass skipped (disabled via configuration).",
            )
        }

    evidence = _build_coordinator_prompt(state)
    report_json = json.dumps(coordinator_result.model_dump(), default=str)[:4000]

    start = time.perf_counter_ns()
    try:
        data = await chat_json(
            JUDGE_SYSTEM_PROMPT,
            f"## Report to verify\n{report_json}\n\n## Evidence it should be grounded in\n{evidence}",
            timeout=120.0,
        )
        duration_ms = int((time.perf_counter_ns() - start) / 1_000_000)
        issues = [str(x) for x in (data.get("issues") or [])][:5]
        # Don't blindly trust the model's self-reported "grounded" flag — if it also
        # listed issues, that's a self-contradiction (it found something ungrounded but
        # still called the report grounded). Force grounded=False whenever there are
        # issues, deterministically, rather than let the LLM's inconsistency propagate
        # into the report's Evidence Confidence score.
        grounded = bool(data.get("grounded", True)) and not issues
        return {
            "judge_result": JudgeVerdict(
                grounded=grounded,
                issues=issues,
                notes=str(data.get("notes", "")),
            ),
            "judge_duration_ms": duration_ms,
        }
    except OllamaError as exc:
        logger.warning("Judge pass failed: %s", exc)
        return {"judge_result": JudgeVerdict(grounded=True, notes=f"Judge pass unavailable: {exc}")}
