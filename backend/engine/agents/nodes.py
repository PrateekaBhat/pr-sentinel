from __future__ import annotations

import functools
import json
import logging
import time

from .. import agent_routing
from ..models import (
    AgentFinding,
    AIAnalysis,
    FileRisk,
    JudgeVerdict,
    RiskFactorFlag,
    RiskLevel,
)
from ..ollama_client import OllamaError, chat_json
from .prompts import (
    AGENT_RESPONSE_INSTRUCTIONS,
    AGENT_SYSTEM_PROMPTS,
    COORDINATOR_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT,
)
from .state import AgentState

logger = logging.getLogger("pr_sentinel.agents")

MAX_PATCH_CHARS = 600
MAX_PATCH_LINES = 30
MAX_FILES_PER_AGENT = 4


def _files_prompt(files) -> str:
    parts = []
    for f in files[:MAX_FILES_PER_AGENT]:
        patch_lines = (f.patch or "").splitlines()[:MAX_PATCH_LINES]
        patch = "\n".join(patch_lines)[:MAX_PATCH_CHARS]
        parts.append(f"### {f.filename} ({f.status}, +{f.additions}/-{f.deletions})\n```diff\n{patch}\n```")
    if len(files) > MAX_FILES_PER_AGENT:
        parts.append(f"... and {len(files) - MAX_FILES_PER_AGENT} more files not shown.")
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

    start = time.perf_counter_ns()
    try:
        system = AGENT_SYSTEM_PROMPTS[domain]
        user = f"## Files in scope\n{_files_prompt(files)}\n{AGENT_RESPONSE_INSTRUCTIONS}"
        data = await chat_json(system, user, timeout=120.0)
        findings = [str(x) for x in (data.get("findings") or [])][:4]
        risk_note = str(data.get("risk_note", ""))
        confidence = int(data.get("confidence", 60))
    except OllamaError as exc:
        logger.warning("%s agent failed: %s", domain, exc)
        findings = []
        risk_note = f"Agent call failed ({exc}); files were not analyzed by AI for this domain."
        confidence = 0
    duration_ms = int((time.perf_counter_ns() - start) / 1_000_000)

    return {
        key: AgentFinding(
            agent=domain,
            label=label,
            applicable=True,
            files_reviewed=[f.filename for f in files],
            findings=findings,
            risk_note=risk_note,
            confidence=confidence,
        ),
        f"{domain}_status": {
            "agent": domain,
            "label": label,
            "status": "Completed",
            "files_reviewed": len(files),
            "duration_ms": duration_ms,
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
        findings_text = "; ".join(finding.findings) if finding.findings else "no concerns raised"
        agent_lines.append(
            f"- {finding.label} (reviewed {len(finding.files_reviewed)} file(s)): "
            f"{findings_text}. Risk note: {finding.risk_note}"
        )

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

    result = AIAnalysis(
        overall_risk=overall_risk,
        confidence=int(data.get("confidence", 60)),
        summary=data.get("summary", ""),
        executive_summary=data.get("executive_summary") or data.get("summary", ""),
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
    it just means no groundedness verdict is attached to the response."""
    coordinator_result = state.get("coordinator_result")
    if coordinator_result is None:
        return {"judge_result": JudgeVerdict(grounded=True, notes="Coordinator produced no output to judge.")}

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
        return {
            "judge_result": JudgeVerdict(
                grounded=bool(data.get("grounded", True)),
                issues=[str(x) for x in (data.get("issues") or [])][:5],
                notes=str(data.get("notes", "")),
            ),
            "judge_duration_ms": duration_ms,
        }
    except OllamaError as exc:
        logger.warning("Judge pass failed: %s", exc)
        return {"judge_result": JudgeVerdict(grounded=True, notes=f"Judge pass unavailable: {exc}")}
