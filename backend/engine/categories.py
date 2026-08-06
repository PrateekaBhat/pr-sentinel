from __future__ import annotations

import re
from typing import Any

from .models import (
    AgentDecision,
    AgentFinding,
    AIAnalysis,
    ArchitecturalImpact,
    ChangedFile,
    ConfidenceExplanation,
    EvidenceItem,
    HeuristicResult,
    PullRequestData,
    RAGContext,
    RiskCategory,
    RiskLevel,
)

# Fixed taxonomy the whole report is scored against. Order matters — it's the order
# categories render in the dashboard and the Markdown report.
CATEGORIES = [
    "Authentication",
    "API",
    "Database",
    "Infrastructure",
    "CI/CD",
    "Dependencies",
    "Secrets",
    "Tests",
    "Documentation",
]

# A file may match more than one pattern; each match contributes evidence to that
# category independently, so a Dockerfile inside .github/workflows can legitimately
# show up under both Infrastructure and CI/CD.
CATEGORY_PATTERNS: dict[str, re.Pattern] = {
    "Authentication": re.compile(r"(^|/)(auth|authn|authz|login|session|jwt|oauth|sso|permissions?|rbac)(/|\.)", re.I),
    "API": re.compile(r"(^|/)(routes?|controllers?|api|graphql|endpoints?|openapi|swagger)(/|\.)", re.I),
    "Database": re.compile(r"(^|/)(migrations?|schema|models?|entity|repository|dao)(/|\.)|\.sql$", re.I),
    "Infrastructure": re.compile(r"(^|/)(terraform|infra|deploy|docker|k8s|kubernetes|helm|ansible)(/|\.)|dockerfile", re.I),
    "CI/CD": re.compile(r"(^|/)(\.github/workflows|\.gitlab-ci|jenkinsfile|\.circleci|\.travis)", re.I),
    "Dependencies": re.compile(r"(^|/)(package(-lock)?\.json|requirements.*\.txt|pyproject\.toml|poetry\.lock|go\.(mod|sum)|pom\.xml|build\.gradle|gemfile|cargo\.(toml|lock)|yarn\.lock)$", re.I),
    "Secrets": re.compile(r"(^|/)(\.env|secrets?|credentials?|vault|\.pem|\.key$|\.p12$)", re.I),
    "Tests": re.compile(r"(^|/)(tests?|__tests__|spec)(/|\.)|\.(test|spec)\.", re.I),
    "Documentation": re.compile(r"(^|/)(readme|docs?/|changelog|architecture)|\.(md|mdx|rst)$", re.I),
}

_SEVERITY_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}

_RECOMMENDED_ACTIONS = {
    "Authentication": "Require an explicit review from someone on the security/auth code-owners group before merge.",
    "API": "Confirm the change is backward compatible or bump the API version; update client SDKs/docs.",
    "Database": "Verify the migration is reversible and run it against a staging copy of production data first.",
    "Infrastructure": "Review the deployment/IaC diff with an SRE and stage the change through a lower environment.",
    "CI/CD": "Dry-run the updated pipeline on a branch before merging to avoid breaking the main build.",
    "Dependencies": "Check the changelog/CVE feed for the bumped packages before approving.",
    "Secrets": "Confirm no plaintext secret was committed; rotate any credential that may have been exposed.",
    "Tests": "Add or restore coverage for the touched code paths before this ships.",
    "Documentation": "No action required beyond a normal doc review.",
}


def _snippet_for(f: ChangedFile, max_lines: int = 6, max_chars: int = 320) -> str | None:
    if not f.patch:
        return None
    lines = [l for l in f.patch.splitlines() if l.startswith("+") or l.startswith("-")][:max_lines]
    return "\n".join(lines)[:max_chars] or None


def classify_files(files: list[ChangedFile]) -> dict[str, list[ChangedFile]]:
    """Deterministically buckets changed files into the fixed category taxonomy."""
    buckets: dict[str, list[ChangedFile]] = {c: [] for c in CATEGORIES}
    for f in files:
        for category, pattern in CATEGORY_PATTERNS.items():
            if pattern.search(f.filename):
                buckets[category].append(f)
    return buckets


# Maps the LLM specialist-agent domains onto the fixed category taxonomy so agent
# findings can enrich the deterministic file-based evidence with reasoning, not just
# a file list.
_AGENT_DOMAIN_TO_CATEGORIES = {
    "security": ["Authentication", "Secrets"],
    "database": ["Database"],
    "api": ["API"],
    "tests": ["Tests"],
    "performance": ["Infrastructure"],
}


def build_category_breakdown(
    pr: PullRequestData,
    heuristics: HeuristicResult,
    ai: AIAnalysis,
) -> list[RiskCategory]:
    """Builds the per-category score breakdown. Deterministic file classification is
    the backbone (so this works even in the heuristics-only fallback path); when agent
    findings are available they enrich the evidence with reasoning and confidence."""
    buckets = classify_files(pr.files)

    file_risk_by_name = {fr.filename: fr for fr in ai.file_risks}
    findings_by_domain = {af.agent: af for af in ai.agent_findings}

    categories: list[RiskCategory] = []
    for category in CATEGORIES:
        files = buckets[category]
        evidence: list[EvidenceItem] = []
        worst = RiskLevel.LOW

        # Pull in reasoning from whichever specialist agent covers this category, if any.
        agent_note = None
        for domain, cats in _AGENT_DOMAIN_TO_CATEGORIES.items():
            if category in cats:
                finding = findings_by_domain.get(domain)
                if finding and finding.applicable:
                    agent_note = finding

        for f in files:
            fr = file_risk_by_name.get(f.filename)
            severity = fr.risk if fr else (RiskLevel.MEDIUM if category in ("Authentication", "Secrets", "Database") else RiskLevel.LOW)
            if _SEVERITY_ORDER[severity] > _SEVERITY_ORDER[worst]:
                worst = severity

            if fr:
                explanation = fr.reason
            elif agent_note and agent_note.findings:
                explanation = agent_note.findings[0]
            else:
                explanation = f"{category} file changed ({f.status}, +{f.additions}/-{f.deletions})."

            confidence = 75 if fr else (agent_note.confidence if agent_note else 50)

            evidence.append(
                EvidenceItem(
                    file_path=f.filename,
                    snippet=_snippet_for(f),
                    explanation=explanation,
                    confidence=confidence,
                    severity=severity,
                    recommended_action=_RECOMMENDED_ACTIONS.get(category, "Review before merge."),
                )
            )

        # Special case: "no tests touched at all" is evidence *for* the Tests category
        # even though no test file was changed.
        if category == "Tests" and not files and not heuristics.tests_touched:
            evidence.append(
                EvidenceItem(
                    file_path="(none — no test files touched)",
                    snippet=None,
                    explanation="This PR changes code but touches no test files.",
                    confidence=90,
                    severity=RiskLevel.MEDIUM,
                    recommended_action=_RECOMMENDED_ACTIONS["Tests"],
                )
            )
            worst = RiskLevel.MEDIUM

        score = min(100, len(evidence) * 15 + (25 if worst == RiskLevel.HIGH else 10 if worst == RiskLevel.MEDIUM else 0))
        if not evidence:
            score = 0
            worst = RiskLevel.LOW

        summary = (
            f"{len(files)} file(s) touched in this category."
            if files
            else "No files in this category were changed."
        )
        if category == "Tests" and not files and not heuristics.tests_touched:
            summary = "No test files were touched by this PR."

        categories.append(
            RiskCategory(
                category=category,
                score=score,
                status=worst,
                summary=summary,
                evidence=evidence,
                reasons=[e.explanation for e in evidence[:5]],
                evidence_files=[f.filename for f in files],
            )
        )

    return categories


def build_architectural_impact(pr: PullRequestData, categories: list[RiskCategory], ai: AIAnalysis) -> ArchitecturalImpact:
    affected = [c.category for c in categories if c.evidence]
    narrative = ai.architectural_impact or (
        f"This change touches {', '.join(affected)}." if affected else "No clearly affected subsystems were detected."
    )
    return ArchitecturalImpact(affected_subsystems=affected, narrative=narrative)


def build_confidence_explanation(
    heuristics: HeuristicResult,
    ai: AIAnalysis,
    rag: RAGContext,
    ai_enabled: bool,
    judge_grounded: bool | None,
) -> ConfidenceExplanation:
    repo_context_available = bool(rag.scanned and rag.retrieved)

    # "Agreement" = the heuristic score band and the LLM's overall_risk band line up.
    heuristic_band = RiskLevel.HIGH if heuristics.score >= 70 else RiskLevel.MEDIUM if heuristics.score >= 35 else RiskLevel.LOW
    agreement = heuristic_band == ai.overall_risk

    all_agents_ran = ai_enabled and all(af.applicable or not af.files_reviewed for af in ai.agent_findings)
    completeness = "complete" if (ai_enabled and repo_context_available and all_agents_ran) else "partial"

    reasons = []
    reasons.append(
        "repository documentation was retrieved and used as context" if repo_context_available
        else "no repository documentation was available to ground the analysis"
    )
    reasons.append(
        "the heuristic score and the LLM's risk assessment agree" if agreement
        else "the heuristic score and the LLM's risk assessment diverge, which was treated as a signal to be more conservative"
    )
    if not ai_enabled:
        reasons.append("the AI pipeline was unavailable, so this is a deterministic heuristics-only assessment")
    elif judge_grounded is False:
        reasons.append("the groundedness judge flagged claims that weren't fully traceable to evidence")
        completeness = "partial"

    narrative = "; ".join(reasons).capitalize() + "."

    score = ai.confidence
    if completeness == "partial":
        score = min(score, 65)
    if judge_grounded is False:
        score = min(score, 55)

    return ConfidenceExplanation(
        score=score,
        repository_context_available=repo_context_available,
        llm_heuristic_agreement=agreement,
        evidence_completeness=completeness,
        narrative=narrative,
    )


def build_agent_decisions(state: dict[str, Any]) -> list[AgentDecision]:
    decisions: list[AgentDecision] = []
    for domain in ["security", "database", "api", "tests", "performance"]:
        status = state.get(f"{domain}_status")
        finding: AgentFinding | None = state.get(f"{domain}_finding")
        if status is None or finding is None:
            continue
        if not finding.applicable:
            decision = "Skipped — no files in this agent's domain were touched"
            reasoning = finding.risk_note
            confidence = 100  # certain there's nothing to review
        elif finding.findings:
            decision = f"Concerns raised ({len(finding.findings)})"
            reasoning = " ".join(finding.findings[:2])
            confidence = finding.confidence
        else:
            decision = "No concerns raised"
            reasoning = finding.risk_note or "Reviewed the relevant files and found nothing actionable."
            confidence = finding.confidence

        decisions.append(
            AgentDecision(
                agent=domain,
                label=status["label"] if isinstance(status, dict) else status.label,
                decision=decision,
                reasoning=reasoning,
                confidence=confidence,
                execution_time_ms=status["duration_ms"] if isinstance(status, dict) else status.duration_ms,
            )
        )
    return decisions
