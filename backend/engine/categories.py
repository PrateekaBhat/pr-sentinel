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
    RiskFactorFlag,
    RiskLevel,
)

# Fixed taxonomy the whole report is scored against. Order matters.
CATEGORIES = [
    "Authentication",
    "API",
    "Data Layer",
    "Infrastructure",
    "CI/CD",
    "Dependencies",
    "Secrets",
    "Tests",
    "Application/Core Logic",
    "Documentation",
]

# ---------------------------------------------------------------------------
# Persistence-layer guard — used to prevent domain/Pydantic model files from
# being classified as Data Layer just because they contain "model" in the path.
# A file is a persistence-layer file only if it has one of these signals:
#   - lives under a migrations/ or alembic/ directory
#   - is a .sql file
#   - is a Prisma schema
#   - is under db/ or database/ (explicit DB subdirectory prefix)
#   - is a Flyway / Liquibase migration
#   - contains an ORM base-class declaration pattern in a db-prefixed path
# ---------------------------------------------------------------------------
_PERSISTENCE_LAYER_RE = re.compile(
    r"""
    (^|/)alembic(/|\.)              # Alembic migration directories
    | (^|/)migrations?(/|\.)        # Django / Flask / SQLAlchemy migrations folder
    | (^|/)flyway(/|\.)             # Flyway
    | (^|/)liquibase(/|\.)          # Liquibase
    | (^|/)prisma(/|\.)             # Prisma schema directory
    | schema\.prisma$               # Prisma schema file by name
    | \.sql$                        # Raw SQL files
    | (^|/)db/models?(/|\.)         # models under an explicit db/ subdirectory
    | (^|/)database/models?(/|\.)   # models under an explicit database/ subdirectory
    | (^|/)entity(/|\.)             # JPA / TypeORM entity classes
    | (^|/)repository(/|\.)         # Repository / DAO pattern
    """,
    re.I | re.VERBOSE,
)


def _is_persistence_layer_file(filename: str) -> bool:
    """True only when there is hard evidence that the file belongs to the database
    / persistence layer. A file named models.py in a general engine/, app/, or
    backend/ directory does NOT qualify unless the path itself carries DB signals."""
    return bool(_PERSISTENCE_LAYER_RE.search(filename))


# Category patterns — broad enough to match by convention, but Data Layer has
# an extra guard (_is_persistence_layer_file) applied in classify_files().
CATEGORY_PATTERNS: dict[str, re.Pattern] = {
    "Authentication": re.compile(
        r"(^|/)(auth|authn|authz|login|session|jwt|oauth|sso|permissions?|rbac)(/|\.)",
        re.I,
    ),
    "API": re.compile(
        r"(^|/)(routes?|controllers?|api|graphql|endpoints?|openapi|swagger)(/|\.)",
        re.I,
    ),
    # Data Layer pattern intentionally conservative — only matches paths that carry
    # explicit persistence-layer vocabulary. "models.py" in an engine/ dir does not match.
    "Data Layer": re.compile(
        r"""
        (^|/)alembic(/|\.)
        | (^|/)migrations?(/|\.)
        | (^|/)flyway(/|\.)
        | (^|/)liquibase(/|\.)
        | (^|/)prisma(/|\.)
        | schema\.prisma$
        | \.sql$
        | (^|/)db/models?(/|\.)
        | (^|/)database/models?(/|\.)
        | (^|/)entity(/|\.)
        | (^|/)repository(/|\.)
        """,
        re.I | re.VERBOSE,
    ),
    "Infrastructure": re.compile(
        r"(^|/)(terraform|infra|deploy|docker|k8s|kubernetes|helm|ansible)(/|\.)|dockerfile",
        re.I,
    ),
    "CI/CD": re.compile(
        r"(^|/)(\.github/workflows|\.gitlab-ci|jenkinsfile|\.circleci|\.travis)",
        re.I,
    ),
    "Dependencies": re.compile(
        r"(^|/)(package(-lock)?\.json|requirements.*\.txt|pyproject\.toml|poetry\.lock"
        r"|go\.(mod|sum)|pom\.xml|build\.gradle|gemfile|cargo\.(toml|lock)|yarn\.lock)$",
        re.I,
    ),
    "Secrets": re.compile(
        r"(^|/)(\.env|secrets?|credentials?|vault|\.pem|\.key$|\.p12$)",
        re.I,
    ),
    "Tests": re.compile(
        r"(^|/)(tests?|__tests__|spec)(/|\.)|\.(test|spec)\.",
        re.I,
    ),
    # General implementation files: engine/, core/, lib/, etc. — catch-all for
    # domain models, service layer, renderers, clients, etc.
    "Application/Core Logic": re.compile(
        r"""
        (^|/)(engine|core|lib|src|app|backend)(/[^/]+)*/
        (models?|services?|utils?|helpers?|handlers?|
        processors?|pipelines?|analyzers?|renderers?|
        clients?|managers?|agent\w*)
        \.(py|ts|js|go|java|rb|rs)$
        """,
        re.I | re.VERBOSE,
    ),
    "Documentation": re.compile(
        r"(^|/)(readme|docs?/|changelog|architecture)|\.(md|mdx|rst)$",
        re.I,
    ),
}

_SEVERITY_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}

_RECOMMENDED_ACTIONS = {
    "Authentication": "Require an explicit review from the security/auth code-owners group before merge.",
    "API": "Confirm the change is backward compatible or bump the API version; update client SDKs/docs.",
    "Data Layer": "Verify the migration is reversible and run it against a staging copy of production data first.",
    "Infrastructure": "Review the deployment/IaC diff with an SRE and stage the change through a lower environment.",
    "CI/CD": "Dry-run the updated pipeline on a branch before merging to avoid breaking the main build.",
    "Dependencies": "Check the changelog/CVE feed for the bumped packages before approving.",
    "Secrets": "Confirm no plaintext secret was committed; rotate any credential that may have been exposed.",
    "Tests": "Add or restore coverage for the touched code paths before this ships.",
    "Application/Core Logic": "Review the logic change for correctness; ensure the affected code paths have test coverage.",
    "Documentation": "No action required beyond a standard doc review.",
}

# Per-category point weight per evidence item. High-sensitivity categories
# contribute more to the score per file; documentation and CI contribute less,
# so a PR that only touches docs/workflow/reports does not dominate the score.
_CATEGORY_EVIDENCE_WEIGHT = {
    "Authentication": 30,
    "API": 25,
    "Data Layer": 25,
    "Infrastructure": 20,
    "CI/CD": 12,
    "Dependencies": 10,
    "Secrets": 35,
    "Tests": 10,
    "Application/Core Logic": 8,
    "Documentation": 5,
}

_SEVERITY_BONUS = {RiskLevel.HIGH: 25, RiskLevel.MEDIUM: 10, RiskLevel.LOW: 0}


def _confidence_label(score: int) -> str:
    """Convert a 0-100 confidence score to a human-readable tier."""
    if score >= 75:
        return "High"
    if score >= 50:
        return "Medium"
    return "Low"


def _snippet_for(f: ChangedFile, max_lines: int = 6, max_chars: int = 320) -> str | None:
    if not f.patch:
        return None
    lines = [l for l in f.patch.splitlines() if l.startswith("+") or l.startswith("-")][:max_lines]
    return "\n".join(lines)[:max_chars] or None


def _explain_file_for_category(f: ChangedFile, category: str) -> str:
    """Generate a human-readable explanation of why a file is relevant to the
    given category. Favours specificity over generic "file changed" language."""
    fname = f.filename.lower()
    change_summary = (
        f"{'added' if f.status == 'added' else 'removed' if f.status == 'removed' else 'modified'}"
        f", +{f.additions}/\u2212{f.deletions} lines"
    )

    if category == "Authentication":
        return (
            f"This file is part of the authentication/authorization layer ({change_summary}). "
            "Changes here can affect session handling, token validation, or access control."
        )
    if category == "API":
        return (
            f"This file defines or modifies API routes, controllers, or endpoint handlers ({change_summary}). "
            "Changes here may alter the public API contract consumed by clients."
        )
    if category == "Data Layer":
        return (
            f"This file contains persistence-layer changes ({change_summary}): "
            "a migration, ORM schema definition, or raw SQL that directly affects the database state."
        )
    if category == "Infrastructure":
        return (
            f"This file configures infrastructure or deployment ({change_summary}). "
            "Changes here can affect how the application is packaged, deployed, or scaled."
        )
    if category == "CI/CD":
        return (
            f"This file defines the CI/CD pipeline ({change_summary}). "
            "Changes here affect how automated tests, builds, and deployments are triggered."
        )
    if category == "Dependencies":
        if "lock" in fname:
            return (
                f"This lock file was updated ({change_summary}), indicating a dependency version change. "
                "Review the diff for removed packages or major version bumps that could introduce "
                "breaking changes or new vulnerabilities."
            )
        return (
            f"This dependency manifest was changed ({change_summary}). "
            "Added, removed, or updated packages may introduce new vulnerabilities or break compatibility."
        )
    if category == "Secrets":
        return (
            f"This file may contain or expose credentials ({change_summary}). "
            "Review carefully to ensure no plaintext secrets were committed."
        )
    if category == "Tests":
        return (
            f"This test file was modified ({change_summary}). "
            "Review whether coverage was added or removed alongside the production code change."
        )
    if category == "Application/Core Logic":
        basename = f.filename.split("/")[-1]
        if "model" in fname:
            return (
                f"This file defines internal domain or data-transfer models ({change_summary}). "
                "No ORM base classes, Alembic migrations, or persistence-layer signals were detected "
                "in this path\u2014this is a Pydantic/dataclass domain model, not a database schema."
            )
        if "report" in fname or "render" in fname:
            return (
                f"This file handles report generation or output rendering ({change_summary}). "
                "Changes here affect how risk assessments are formatted and presented."
            )
        if "service" in fname:
            return (
                f"This file contains service-layer orchestration logic ({change_summary}). "
                "Review for correctness of the changed business rules or data flow."
            )
        if "client" in fname:
            return (
                f"This file is an external client adapter ({change_summary}). "
                "Review changes to API calls, retry logic, or error-handling behaviour."
            )
        if "agent" in fname:
            return (
                f"This file is part of the LangGraph agent pipeline ({change_summary}). "
                "Changes here affect specialist-agent routing, prompts, or coordinator synthesis."
            )
        return (
            f"This is a core implementation file ({change_summary}). "
            f"Review the changed logic in `{basename}` for correctness and test coverage."
        )
    if category == "Documentation":
        return (
            f"This documentation file was {f.status} ({change_summary}). "
            "No runtime or production code was changed by this file."
        )
    return f"{category} file changed ({change_summary})."


def classify_files(files: list[ChangedFile]) -> dict[str, list[ChangedFile]]:
    """Deterministically buckets changed files into the fixed category taxonomy.

    Key invariant enforced here:
    - A file named models.py in engine/, app/, or a general backend directory is
      classified as Application/Core Logic, NOT Data Layer, unless the path itself
      contains migration/sql/alembic/prisma signals.
    - Unmatched implementation files (.py/.ts/.js/.go) fall into Application/Core Logic
      as a safe catch-all rather than being silently dropped.
    """
    buckets: dict[str, list[ChangedFile]] = {c: [] for c in CATEGORIES}
    for f in files:
        matched_specific = False
        for category, pattern in CATEGORY_PATTERNS.items():
            if category == "Application/Core Logic":
                # Applied as fallback below; skip in the primary pass.
                continue
            if not pattern.search(f.filename):
                continue
            # Extra guard: Data Layer requires hard persistence-layer evidence.
            if category == "Data Layer" and not _is_persistence_layer_file(f.filename):
                continue
            buckets[category].append(f)
            matched_specific = True

        # Application/Core Logic: match the pattern OR fall back for any unmatched
        # implementation file so nothing is silently dropped from the report.
        app_pattern = CATEGORY_PATTERNS["Application/Core Logic"]
        if app_pattern.search(f.filename) or (
            not matched_specific
            and re.search(r"\.(py|ts|js|go|java|rb|rs)$", f.filename, re.I)
        ):
            buckets["Application/Core Logic"].append(f)

    return buckets


# Maps the LLM specialist-agent domains onto the fixed category taxonomy so agent
# findings can enrich the deterministic file-based evidence with reasoning.
_AGENT_DOMAIN_TO_CATEGORIES = {
    "security": ["Authentication", "Secrets"],
    "database": ["Data Layer"],
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

        # Pull in reasoning from whichever specialist agent covers this category.
        agent_note = None
        for domain, cats in _AGENT_DOMAIN_TO_CATEGORIES.items():
            if category in cats:
                finding = findings_by_domain.get(domain)
                if finding and finding.applicable:
                    agent_note = finding

        for f in files:
            fr = file_risk_by_name.get(f.filename)
            # Authentication/Secrets/Data Layer default to MEDIUM when unreviewed;
            # all other categories default to LOW.
            if fr:
                severity = fr.risk
            elif category in ("Authentication", "Secrets", "Data Layer"):
                severity = RiskLevel.MEDIUM
            else:
                severity = RiskLevel.LOW

            if _SEVERITY_ORDER[severity] > _SEVERITY_ORDER[worst]:
                worst = severity

            # Evidence explanation: prefer LLM reasoning → agent finding → deterministic label.
            if fr and fr.reason:
                explanation = fr.reason
            elif agent_note and agent_note.findings:
                explanation = agent_note.findings[0]
            else:
                explanation = _explain_file_for_category(f, category)

            # Confidence: High if LLM reviewed; Medium if an agent covered the domain;
            # Low if purely path-heuristic.
            if fr:
                raw_confidence = 75
            elif agent_note:
                raw_confidence = agent_note.confidence
            else:
                raw_confidence = 50

            evidence.append(
                EvidenceItem(
                    file_path=f.filename,
                    snippet=_snippet_for(f),
                    explanation=explanation,
                    confidence=raw_confidence,
                    severity=severity,
                    recommended_action=_RECOMMENDED_ACTIONS.get(category, "Review before merge."),
                )
            )

        # Special case: no tests touched is evidence for the Tests category.
        if category == "Tests" and not files and not heuristics.tests_touched:
            evidence.append(
                EvidenceItem(
                    file_path="(no test files touched)",
                    snippet=None,
                    explanation=(
                        "This PR modifies implementation files but does not add or update any "
                        "test files. Confirm whether the changed logic paths are covered by "
                        "existing tests, or whether new tests are warranted."
                    ),
                    confidence=85,
                    severity=RiskLevel.MEDIUM,
                    recommended_action=_RECOMMENDED_ACTIONS["Tests"],
                )
            )
            worst = RiskLevel.MEDIUM

        # Calibrated scoring: per-item weight varies by category sensitivity,
        # plus a severity bonus. This prevents low-sensitivity categories like
        # Documentation from dominating the overall score.
        weight = _CATEGORY_EVIDENCE_WEIGHT.get(category, 8)
        score = min(100, len(evidence) * weight + _SEVERITY_BONUS.get(worst, 0))
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


def build_architectural_impact(
    pr: PullRequestData,
    categories: list[RiskCategory],
    ai: AIAnalysis,
) -> ArchitecturalImpact:
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

    heuristic_band = (
        RiskLevel.HIGH if heuristics.score >= 70
        else RiskLevel.MEDIUM if heuristics.score >= 35
        else RiskLevel.LOW
    )
    agreement = heuristic_band == ai.overall_risk

    all_agents_ran = ai_enabled and all(af.applicable or not af.files_reviewed for af in ai.agent_findings)
    completeness = "complete" if (ai_enabled and repo_context_available and all_agents_ran) else "partial"

    reasons = []
    reasons.append(
        "Repository documentation was retrieved and used as context"
        if repo_context_available
        else "No repository documentation was available to ground the analysis"
    )
    reasons.append(
        "the heuristic score and the LLM's risk assessment agree"
        if agreement
        else "the heuristic score and the LLM's risk assessment diverge; a conservative bias was applied"
    )
    if not ai_enabled:
        reasons.append("the AI pipeline was unavailable; this is a deterministic heuristics-only assessment")
    elif judge_grounded is False:
        reasons.append("the groundedness judge flagged claims that weren't fully traceable to evidence")
        completeness = "partial"

    narrative = "; ".join(reasons) + "."

    score = ai.confidence
    if completeness == "partial":
        score = min(score, 65)
    if judge_grounded is False:
        score = min(score, 55)

    level = _confidence_label(score)

    checks = [
        RiskFactorFlag(key="repo_docs", label="Repository documentation found", passed=repo_context_available),
        RiskFactorFlag(key="heuristic_llm_agree", label="Heuristic and LLM assessments agree", passed=agreement),
        RiskFactorFlag(key="agents_completed", label="All applicable specialist agents completed", passed=all_agents_ran),
        RiskFactorFlag(key="ai_available", label="AI pipeline was available", passed=ai_enabled),
        RiskFactorFlag(key="grounded", label="Groundedness check passed", passed=bool(judge_grounded) if judge_grounded is not None else True),
    ]

    return ConfidenceExplanation(
        score=score,
        level=level,
        repository_context_available=repo_context_available,
        llm_heuristic_agreement=agreement,
        evidence_completeness=completeness,
        narrative=narrative,
        checks=checks,
    )


def build_agent_decisions(state: dict[str, Any]) -> list[AgentDecision]:
    decisions: list[AgentDecision] = []
    for domain in ["security", "database", "api", "tests", "performance"]:
        status = state.get(f"{domain}_status")
        finding: AgentFinding | None = state.get(f"{domain}_finding")
        if status is None or finding is None:
            continue
        if not finding.applicable:
            decision = "Skipped \u2014 no files in this agent\u2019s domain were touched"
            reasoning = finding.risk_note
            confidence = 100
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
