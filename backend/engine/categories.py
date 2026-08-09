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
    SpecialistRoutingEntry,
)
from .policy import classify_release_risk

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
    """Evidence Confidence tier — not a calibrated probability."""
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
            elif agent_note and agent_note.structured_findings:
                explanation = agent_note.structured_findings[0].title
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
    llm_disagreement_detected: bool = False,
) -> ConfidenceExplanation:
    repo_context_available = bool(rag.scanned and rag.retrieved)

    deterministic_risk = classify_release_risk(heuristics.score)
    agreement = deterministic_risk == ai.overall_risk if ai_enabled else True

    applicable_agents = [af for af in ai.agent_findings if af.applicable]
    all_agents_ran = ai_enabled and all(
        af.applicable or not af.files_reviewed for af in ai.agent_findings
    )

    completeness = "complete" if (ai_enabled and repo_context_available and all_agents_ran) else "partial"

    reasons = []
    if not ai_enabled:
        reasons.append("AI synthesis unavailable — deterministic policy produced the release decision")
    if repo_context_available:
        reasons.append("repository context was retrieved")
    else:
        reasons.append("repository context was unavailable")
    if agreement:
        reasons.append("LLM assessment agrees with deterministic release risk")
    elif ai_enabled:
        reasons.append("LLM assessment diverges from deterministic policy (override active)")
    if judge_grounded is False:
        reasons.append("groundedness check failed — review explanation quality separately from release policy")

    narrative = "; ".join(reasons) + "."

    # Evidence Confidence tier — deterministic checks
    checks = [
        RiskFactorFlag(key="deterministic", label="Deterministic analysis available", passed=True),
        RiskFactorFlag(key="repo_docs", label="Repository context available", passed=repo_context_available),
        RiskFactorFlag(
            key="specialists",
            label="Applicable specialists completed",
            passed=bool(applicable_agents) if ai_enabled else False,
        ),
        RiskFactorFlag(key="ai_available", label="AI synthesis available", passed=ai_enabled),
        RiskFactorFlag(
            key="grounded",
            label="Groundedness check passed",
            passed=bool(judge_grounded) if judge_grounded is not None else (not ai_enabled),
        ),
        RiskFactorFlag(
            key="no_major_gaps",
            label="No major evidence gaps",
            passed=ai_enabled and completeness == "complete" and judge_grounded is not False,
        ),
    ]

    passed_count = sum(1 for c in checks if c.passed)
    if not ai_enabled:
        score = 45
        level = "LOW"
    elif passed_count >= 5 and agreement and judge_grounded is not False:
        score = 85
        level = "HIGH"
    elif passed_count >= 3:
        score = 60
        level = "MEDIUM"
    else:
        score = 40
        level = "LOW"

    if llm_disagreement_detected:
        score = min(score, 65)
        if level == "HIGH":
            level = "MEDIUM"

    return ConfidenceExplanation(
        score=score,
        level=level,
        repository_context_available=repo_context_available,
        llm_heuristic_agreement=agreement,
        evidence_completeness=completeness,
        narrative=narrative,
        checks=checks,
    )


_DOMAIN_SKIP_TRIGGERS = {
    "security": "no authentication, session, or payment-related files detected",
    "database": "no database/schema/migration files detected",
    "api": "no API routes, controllers, or endpoint files detected",
    "tests": "no test or spec files detected",
    "performance": "no cache, queue, or performance-related files detected",
}

_DOMAIN_EXECUTE_TRIGGERS = {
    "security": "authentication or security-sensitive files changed",
    "database": "database migration or schema files changed",
    "api": "API routes or controller files changed",
    "tests": "test or spec files changed",
    "performance": "performance or cache-related files changed",
}


def build_specialist_routing(state: dict[str, Any], pr: PullRequestData) -> list[SpecialistRoutingEntry]:
    """Explainable specialist routing — EXECUTED vs SKIPPED with triggers."""
    from . import agent_routing

    entries: list[SpecialistRoutingEntry] = []
    for domain in ["security", "database", "api", "tests", "performance"]:
        status = state.get(f"{domain}_status")
        finding: AgentFinding | None = state.get(f"{domain}_finding")
        label = agent_routing.DOMAIN_LABELS[domain]
        domain_files = agent_routing.files_for_domain(pr.files, domain)
        file_names = [f.filename for f in domain_files]

        if status is None and finding is None:
            continue

        if finding and finding.applicable:
            duration = status["duration_ms"] if isinstance(status, dict) else (status.duration_ms if status else 0)
            # `status` (set in agents/nodes.py) carries the real available/selected
            # counts for this run. Demo-reconstructed states (see enrich.py) may not
            # have the newer fields, so fall back to what we can infer.
            if isinstance(status, dict):
                files_selected = status.get("files_reviewed", len(getattr(finding, "files_reviewed", []) or []))
                files_available = status.get("files_available", len(file_names))
                context_bounded = status.get("context_bounded", files_available > files_selected)
            else:
                files_selected = len(getattr(finding, "files_reviewed", []) or [])
                files_available = len(file_names)
                context_bounded = files_available > files_selected
            entries.append(
                SpecialistRoutingEntry(
                    domain=domain,
                    label=label,
                    status="EXECUTED",
                    trigger=_DOMAIN_EXECUTE_TRIGGERS.get(domain, f"{domain} domain files detected"),
                    files_count=files_selected,
                    duration_ms=duration,
                    llm_call_made=True,
                    files=(getattr(finding, "files_reviewed", None) or file_names)[:5],
                    files_available=files_available,
                    files_selected=files_selected,
                    context_bounded=context_bounded,
                )
            )
        else:
            entries.append(
                SpecialistRoutingEntry(
                    domain=domain,
                    label=label,
                    status="SKIPPED",
                    trigger=_DOMAIN_SKIP_TRIGGERS.get(domain, f"no {domain} domain files detected"),
                    files_count=0,
                    duration_ms=0,
                    llm_call_made=False,
                    files=[],
                )
            )
    return entries


_BLANKET_REASSURANCE_RE = re.compile(
    r"no concerning issues|nothing concerning|no issues (were )?found|no concerns (were )?"
    r"(found|raised|identified)|no (significant |major |real )?(risks?|problems?) (were )?"
    r"(found|identified|detected)",
    re.I,
)

# Some local LLMs echo the response schema's placeholder tokens back verbatim instead
# of replacing them (e.g. returning "<short, specific finding>: Renamed endpoint x"
# instead of just "Renamed endpoint x"). Strip these schema artifacts defensively so
# they never reach the rendered report.
_PLACEHOLDER_ARTIFACT_RE = re.compile(r"<[^<>]{0,60}>:?\s*", re.I)


def clean_finding_text(text: str) -> str:
    """Strip literal prompt-template placeholders an LLM echoed back verbatim."""
    cleaned = _PLACEHOLDER_ARTIFACT_RE.sub("", text or "").strip()
    return cleaned


def reconcile_executive_summary(summary: str, agent_findings: list[AgentFinding]) -> str:
    """Deterministic guardrail, independent of whether the LLM followed the prompt's
    consistency/grounding rules:

    1. Any specialist domain the summary references must have actually run and be
       applicable — a mention of a domain that was SKIPPED (not applicable) is by
       definition fabricated, since that agent reviewed nothing. Sentences making such
       a claim are removed outright.
    2. If specialist.concerns > 0, that specialist's finding MUST appear in the summary.
       If specialist.concerns == 0, the specialist may be described as clean.
    3. A blanket reassurance ("no concerning issues found") is never allowed to coexist
       with a specialist that actually raised concerns.

    This never rewrites a summary that's already accurate; it only removes what's
    fabricated and appends what's missing.
    """
    text = summary or ""

    # `structured_findings` is the authoritative, validated representation of what a
    # specialist actually found — reconciliation is deliberately checked against it
    # rather than the legacy `findings` string list, so a finding the validation layer
    # rejected can never be reintroduced here just because it once existed in raw form.
    with_concerns = [f for f in agent_findings if f.applicable and f.structured_findings]
    skipped_labels = [f.label for f in agent_findings if not f.applicable]

    def _split_sentences(t: str) -> list[str]:
        return [s for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]

    # 1. Remove sentences that attribute findings to a domain that never ran.
    if skipped_labels:
        kept = []
        for s in _split_sentences(text):
            if any(re.search(re.escape(label), s, re.I) for label in skipped_labels):
                continue
            kept.append(s)
        text = " ".join(kept).strip()

    if not with_concerns:
        # No real concerns to reconcile against — but a blanket "no concerns" claim is
        # still fine to leave as-is here, since it isn't contradicted by anything.
        return text

    # 2. Decide, against the *current* text, which concerned specialists are actually
    #    and accurately addressed: mentioned by name, in a sentence that isn't just a
    #    reassurance ("no risks found") sitting next to the name.
    def _sentence_addresses_concern(label: str) -> bool:
        for s in _split_sentences(text):
            if re.search(re.escape(label), s, re.I) and not _BLANKET_REASSURANCE_RE.search(s):
                return True
        return False

    missing = [f for f in with_concerns if not _sentence_addresses_concern(f.label)]

    # 3. Now clean up: drop any sentence that pairs a *missing* specialist's name with a
    #    reassuring phrase (actively misleading), and strip any remaining blanket
    #    reassurance clauses that aren't tied to a specific specialist at all.
    cleaned = []
    for s in _split_sentences(text):
        misleads_a_missing_one = any(
            re.search(re.escape(f.label), s, re.I) for f in missing
        ) and _BLANKET_REASSURANCE_RE.search(s)
        if misleads_a_missing_one:
            continue
        if _BLANKET_REASSURANCE_RE.search(s):
            clauses = re.split(r",\s*(?:but|and)\s+", s)
            surviving = [c for c in clauses if not _BLANKET_REASSURANCE_RE.search(c)]
            if surviving:
                clause = surviving[0].strip().rstrip(" .,;")
                if clause:
                    cleaned.append(clause + ".")
            continue
        cleaned.append(s)
    text = " ".join(cleaned).strip()

    if not missing:
        return text

    addendum_parts = []
    for f in missing:
        # Titles on structured_findings are already validated/cleaned — no need to
        # re-run clean_finding_text, and no unvalidated text can reach this addendum.
        titles = [sf.title for sf in f.structured_findings[:2] if sf.title]
        detail = "; ".join(titles) if titles else (f.risk_note or "see agent findings")
        addendum_parts.append(f"{f.label} raised {len(f.structured_findings)} concern(s): {detail}.")

    if text and not text.endswith((".", "!", "?")):
        text += "."
    return f"{text} {' '.join(addendum_parts)}".strip()


def build_agent_decisions(state: dict[str, Any]) -> list[AgentDecision]:
    decisions: list[AgentDecision] = []
    for domain in ["security", "database", "api", "tests", "performance"]:
        status = state.get(f"{domain}_status")
        finding: AgentFinding | None = state.get(f"{domain}_finding")
        if status is None or finding is None:
            continue
        if not finding.applicable:
            decision = "SKIPPED — no files in domain"
            reasoning = f"Trigger: {_DOMAIN_SKIP_TRIGGERS.get(domain, 'no matching files')}. LLM call: not made."
            confidence = 100
        elif finding.structured_findings:
            # structured_findings is the authoritative, validated source — counts and
            # rendered reasoning are derived from it, never from the raw/legacy list.
            decision = f"Concerns raised ({len(finding.structured_findings)})"
            reasoning = " ".join(sf.title for sf in finding.structured_findings[:2])
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
