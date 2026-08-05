from __future__ import annotations

import json
import re

import httpx

from .config import get_settings
from .models import AIAnalysis, FileRisk, HeuristicResult, PullRequestData, RiskFactorFlag, RiskLevel

MAX_FILES_IN_PROMPT = 25
MAX_PATCH_CHARS = 1200


class OllamaError(Exception):
    """Raised when Ollama can't be reached or returns an unusable response."""


SYSTEM_PROMPT = """You are a senior Staff Engineer performing a pre-merge risk review of a pull request.

Do NOT review code style, naming, or formatting. Instead determine:
- overall production risk
- architectural impact
- a rollout recommendation (e.g. standard merge, canary, feature-flagged, staged rollout)
- whether a rollback plan should be required
- concrete testing recommendations
- operational risks (on-call load, monitoring gaps, blast radius)

You are given deterministic heuristic findings alongside the raw diff. Treat the heuristics as
signal, not ground truth — you may agree, disagree, or add nuance, but explain your reasoning
grounded in the actual files and diff content, not just the heuristic labels.

Respond with ONLY a single JSON object (no markdown fences, no prose before or after) matching
exactly this shape:

{
  "overall_risk": "LOW" | "MEDIUM" | "HIGH",
  "confidence": <integer 0-100>,
  "summary": "<2-3 sentence plain-English summary of the risk>",
  "architectural_impact": "<1-2 sentences>",
  "operational_risks": ["<short phrase>", ...],
  "rollout_strategy": "<short label, e.g. 'Canary' | 'Standard merge' | 'Feature-flagged rollout' | 'Staged rollout'>",
  "rollout_reason": "<1-2 sentences justifying the strategy>",
  "rollback_required": <true|false>,
  "test_coverage_estimate_pct": <integer 0-100 or null>,
  "suggested_test_areas": ["<short phrase>", ...],
  "risk_factors": [ {"key": "<snake_case>", "label": "<short label>", "passed": <true|false>}, ... ],
  "file_risks": [ {"filename": "<path>", "risk": "LOW"|"MEDIUM"|"HIGH", "reason": "<short reason>"}, ... ]
}

Limit file_risks to the 5 files most likely to cause production issues. Limit risk_factors to at
most 6 of the most relevant categories (e.g. authentication, payments, configuration,
infrastructure, tests, database). Keep every string field concise."""


def _build_user_prompt(pr: PullRequestData, heuristics: HeuristicResult) -> str:
    files_section = []
    for f in pr.files[:MAX_FILES_IN_PROMPT]:
        patch = (f.patch or "")[:MAX_PATCH_CHARS]
        files_section.append(
            f"### {f.filename} ({f.status}, +{f.additions}/-{f.deletions})\n```diff\n{patch}\n```"
        )
    if len(pr.files) > MAX_FILES_IN_PROMPT:
        files_section.append(f"... and {len(pr.files) - MAX_FILES_IN_PROMPT} more files not shown.")

    heuristic_lines = [
        f"- {factor.label}: {'TRIGGERED' if factor.triggered else 'not triggered'} ({factor.reason})"
        for factor in heuristics.factors
    ]

    return f"""## Pull Request
Repo: {pr.owner}/{pr.repo}
Title: {pr.title}
Author: {pr.author}
Labels: {', '.join(pr.labels) or 'none'}
Files changed: {pr.changed_files_count} (+{pr.additions}/-{pr.deletions})

Description:
{pr.body or '(no description provided)'}

Commit messages:
{chr(10).join('- ' + m.splitlines()[0] for m in pr.commit_messages) or '(none)'}

## Deterministic heuristic findings (score: {heuristics.score}/100)
{chr(10).join(heuristic_lines)}

## Changed files and diffs
{chr(10).join(files_section)}
"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model response")
    return json.loads(text[start : end + 1])


async def analyze_with_ai(pr: PullRequestData, heuristics: HeuristicResult) -> AIAnalysis:
    settings = get_settings()

    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "format": "json",  # asks Ollama to constrain sampling to valid JSON
        "options": {"temperature": 0.2},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(pr, heuristics)},
        ],
    }

    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=300.0) as client:
            resp = await client.post("/api/chat", json=payload)
    except httpx.ConnectError as exc:
        raise OllamaError(
            f"Couldn't reach Ollama at {settings.ollama_base_url}. "
            "Is it running? Try `ollama serve` in another terminal."
        ) from exc
    except httpx.TimeoutException as exc:
        raise OllamaError(
            "Ollama timed out. Large diffs on CPU-only machines can be slow — "
            "try a smaller/faster model (e.g. `llama3.2`) or a smaller PR."
        ) from exc

    if resp.status_code == 404:
        raise OllamaError(
            f"Model '{settings.ollama_model}' isn't pulled yet. Run: "
            f"`ollama pull {settings.ollama_model}`"
        )
    if resp.status_code >= 400:
        raise OllamaError(f"Ollama error ({resp.status_code}): {resp.text[:300]}")

    body = resp.json()
    text = body.get("message", {}).get("content", "")
    if not text:
        raise OllamaError("Ollama returned an empty response.")

    try:
        data = _extract_json(text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise OllamaError(
            "Model output wasn't valid JSON. Local models occasionally drift from the "
            "requested format — retrying the request, or using a larger model, usually helps."
        ) from exc

    try:
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

        return AIAnalysis(
            overall_risk=overall_risk,
            confidence=int(data.get("confidence", 60)),
            summary=data.get("summary", ""),
            architectural_impact=data.get("architectural_impact", ""),
            operational_risks=data.get("operational_risks", []) or [],
            rollout_strategy=data.get("rollout_strategy", "Standard merge"),
            rollout_reason=data.get("rollout_reason", ""),
            rollback_required=bool(data.get("rollback_required", False)),
            test_coverage_estimate_pct=data.get("test_coverage_estimate_pct"),
            suggested_test_areas=data.get("suggested_test_areas", []) or [],
            risk_factors=risk_factors,
            file_risks=file_risks,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise OllamaError(f"Model returned JSON in an unexpected shape: {exc}") from exc


def analyze_with_heuristics_only(
    pr: PullRequestData, heuristics: HeuristicResult, reason: str = ""
) -> AIAnalysis:
    """Fallback used when Ollama isn't reachable/configured, so the app still works end to end."""
    if heuristics.score >= 60:
        risk = RiskLevel.HIGH
    elif heuristics.score >= 30:
        risk = RiskLevel.MEDIUM
    else:
        risk = RiskLevel.LOW

    triggered = [f for f in heuristics.factors if f.triggered]
    top_files = sorted(pr.files, key=lambda f: f.changes, reverse=True)[:5]

    fallback_note = reason or "Ollama isn't configured."

    return AIAnalysis(
        overall_risk=risk,
        confidence=55,
        summary=(
            f"Heuristic-only analysis ({fallback_note}): "
            f"{len(triggered)} risk signal(s) triggered across {pr.changed_files_count} changed file(s)."
        ),
        architectural_impact="Start Ollama and pull a model (see backend/.env.example) for a full AI-generated assessment.",
        operational_risks=[f.label for f in triggered][:5],
        rollout_strategy="Canary" if risk != RiskLevel.LOW else "Standard merge",
        rollout_reason="Based on deterministic rule score only; enable AI analysis for a reasoned recommendation.",
        rollback_required=risk == RiskLevel.HIGH,
        test_coverage_estimate_pct=None,
        suggested_test_areas=["Integration tests", "Regression"] if not heuristics.tests_touched else ["Regression"],
        risk_factors=[
            RiskFactorFlag(key=f.key, label=f.label, passed=not f.triggered) for f in heuristics.factors
        ],
        file_risks=[
            FileRisk(
                filename=f.filename,
                risk=RiskLevel.HIGH if f.changes > 200 else RiskLevel.MEDIUM,
                reason=f"{f.additions} additions / {f.deletions} deletions in this file.",
            )
            for f in top_files
        ],
    )
