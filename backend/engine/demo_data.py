"""Curated demo PRs.

These are synthetic (not fetched from real repos) so the gallery is fast, free, and
deterministic to demo, while the app still supports analyzing any real public PR by URL
via /api/analyze. Each entry is a fully-formed AnalyzeResponse payload.
"""
from __future__ import annotations

from .categories import build_agent_decisions
from .models import (
    AgentFinding,
    AIAnalysis,
    AnalyzeResponse,
    ArchitecturalImpact,
    ChangedFile,
    ConfidenceExplanation,
    DemoSummary,
    DeploymentRecommendation,
    FileRisk,
    HeuristicFactor,
    HeuristicResult,
    JudgeVerdict,
    PullRequestData,
    RAGChunk,
    RAGContext,
    RepositoryMetadata,
    RiskFactorFlag,
    RiskLevel,
    RiskReport,
    TimelineStage,
    AgentStatus,
)

DEMOS: dict[str, AnalyzeResponse] = {
    "auth-refactor": AnalyzeResponse(
        source="demo",
        ai_enabled=True,
        rag=RAGContext(
            scanned=True,
            default_branch="main",
            indexed_files=3,
            chunks_indexed=11,
            retrieved=[
                RAGChunk(
                    path="docs/architecture.md",
                    snippet="Auth: all services validate sessions via the shared SessionStore "
                    "cookie middleware. Any change to this path requires a security review "
                    "and a canary rollout per the deployment playbook.",
                    score=0.88,
                ),
                RAGChunk(
                    path="CONTRIBUTING.md",
                    snippet="PRs touching auth/ must include integration tests covering both "
                    "the happy path and token-expiry/refresh failure modes.",
                    score=0.81,
                ),
            ],
        ),
        judge=JudgeVerdict(
            grounded=True,
            issues=[],
            notes="Every claim traces to the security agent's findings, the heuristic "
            "factors, or the retrieved architecture doc.",
        ),
        pr=PullRequestData(
            owner="acme",
            repo="orders-service",
            number=421,
            title="Migrate session validation to PingFederate JWT introspection",
            body="Replaces the legacy session-cookie auth middleware with JWT introspection "
            "against PingFederate. Removes the old `SessionStore` and its tests.",
            author="rpatel",
            url="https://github.com/acme/orders-service/pull/421",
            created_at="2024-06-01T12:00:00Z",
            mergeable_state="clean",
            mergeable=True,
            state="open",
            repository={
                "owner": "acme",
                "name": "orders-service",
                "full_name": "acme/orders-service",
                "description": "Order service for the Acme platform.",
                "primary_language": "TypeScript",
                "stars": 58,
                "topics": ["security", "payments"],
                "default_branch": "main",
            },
            additions=312,
            deletions=188,
            changed_files_count=9,
            labels=["security", "backend"],
            commit_messages=[
                "Add JWT introspection client",
                "Swap auth middleware to use introspection client",
                "Remove legacy SessionStore",
            ],
            files=[
                ChangedFile(filename="auth/middleware.ts", status="modified", additions=94, deletions=61, changes=155),
                ChangedFile(filename="auth/jwt_introspection_client.ts", status="added", additions=110, deletions=0, changes=110),
                ChangedFile(filename="auth/session_store.ts", status="removed", additions=0, deletions=98, changes=98),
                ChangedFile(filename="auth/session_store.test.ts", status="removed", additions=0, deletions=29, changes=29),
                ChangedFile(filename="config/auth.yaml", status="modified", additions=12, deletions=4, changes=16),
                ChangedFile(filename="routes/checkout.ts", status="modified", additions=8, deletions=6, changes=14),
            ],
        ),
        heuristics=HeuristicResult(
            score=78,
            tests_touched=False,
            tests_deleted=True,
            migration_touched=False,
            factors=[
                HeuristicFactor(key="auth", label="Authentication logic touched", triggered=True, weight=40, reason="Matched in auth/middleware.ts"),
                HeuristicFactor(key="config", label="Configuration files changed", triggered=True, weight=30, reason="Matched in config/auth.yaml"),
                HeuristicFactor(key="tests_deleted", label="Test files were deleted", triggered=True, weight=25, reason="auth/session_store.test.ts removed with no replacement."),
                HeuristicFactor(key="api_contract", label="Public API contract changed", triggered=False, weight=25, reason="No matching files in this diff."),
            ],
        ),
        ai=AIAnalysis(
            overall_risk=RiskLevel.HIGH,
            confidence=91,
            summary="This PR swaps the authentication mechanism for the entire service and deletes "
            "the only tests covering the old path without adding equivalent coverage for the new one. "
            "A regression here would lock out or falsely authenticate every user.",
            architectural_impact="Centralizes auth on an external identity provider (PingFederate), "
            "trading a local trust boundary for a network dependency on every request.",
            operational_risks=[
                "New hard dependency on PingFederate availability for every authenticated request",
                "No fallback path if introspection calls time out",
                "Session invalidation semantics may differ from the old cookie store",
            ],
            rollout_strategy="Canary",
            rollout_reason="Critical auth-path logic changed with reduced test coverage; a small-percentage "
            "canary with auth-failure-rate alerting will surface regressions before full rollout.",
            rollback_required=True,
            test_coverage_estimate_pct=62,
            suggested_test_areas=["Integration tests", "Authentication", "API contract", "Regression"],
            risk_factors=[
                RiskFactorFlag(key="authentication", label="Authentication", passed=False),
                RiskFactorFlag(key="payment", label="Payment", passed=True),
                RiskFactorFlag(key="configuration", label="Configuration", passed=False),
                RiskFactorFlag(key="infrastructure", label="Infrastructure", passed=True),
                RiskFactorFlag(key="tests", label="Tests", passed=False),
            ],
            file_risks=[
                FileRisk(filename="auth/middleware.ts", risk=RiskLevel.HIGH, reason="Core request-path auth logic rewritten."),
                FileRisk(filename="auth/session_store.ts", risk=RiskLevel.HIGH, reason="Removed with no equivalent test coverage added elsewhere."),
                FileRisk(filename="config/auth.yaml", risk=RiskLevel.MEDIUM, reason="Config drift risk between environments."),
            ],
            agent_findings=[
                AgentFinding(
                    agent="security",
                    label="Security",
                    applicable=True,
                    files_reviewed=["auth/middleware.ts", "auth/jwt_introspection_client.ts", "auth/session_store.ts"],
                    findings=[
                        "New introspection client has no retry/backoff on PingFederate timeouts",
                        "No fallback auth path if the identity provider is unreachable",
                    ],
                    risk_note="Auth mechanism is fully replaced with reduced test coverage — high risk.",
                ),
                AgentFinding(
                    agent="database",
                    label="Database",
                    applicable=False,
                    risk_note="No files in this domain were touched by this PR.",
                ),
                AgentFinding(
                    agent="api",
                    label="API Compatibility",
                    applicable=True,
                    files_reviewed=["routes/checkout.ts"],
                    findings=["checkout route now depends on the new auth middleware indirectly"],
                    risk_note="No request/response shape changes; low direct API risk.",
                ),
                AgentFinding(
                    agent="tests",
                    label="Test Coverage",
                    applicable=True,
                    files_reviewed=["auth/session_store.test.ts"],
                    findings=["Only existing auth tests were deleted; no new tests were added for the introspection client"],
                    risk_note="Net loss of auth test coverage on the exact path being changed.",
                ),
                AgentFinding(
                    agent="performance",
                    label="Performance",
                    applicable=False,
                    risk_note="No files in this domain were touched by this PR.",
                ),
            ],
            citations=[
                RAGChunk(
                    path="docs/architecture.md",
                    snippet="Auth: all services validate sessions via the shared SessionStore "
                    "cookie middleware. Any change to this path requires a security review "
                    "and a canary rollout per the deployment playbook.",
                    score=0.88,
                ),
                RAGChunk(
                    path="CONTRIBUTING.md",
                    snippet="PRs touching auth/ must include integration tests covering both "
                    "the happy path and token-expiry/refresh failure modes.",
                    score=0.81,
                ),
            ],
        ),
        report=RiskReport(
            decision="BLOCK",
            risk_score=78,
            confidence=91,
            deployment_strategy="Canary",
            risk_breakdown={
                "Authentication": 40,
                "Configuration": 30,
                "Tests": 25,
            },
            findings=[
                "Authentication logic touched",
                "Configuration files changed",
                "Test files were deleted",
            ],
            evidence=[
                "Authentication logic touched: Matched in auth/middleware.ts",
                "Configuration files changed: Matched in config/auth.yaml",
                "auth/session_store.ts: Removed with no equivalent test coverage added elsewhere.",
            ],
            timeline=[
                TimelineStage(stage="Repository Loaded", duration_ms=50),
                TimelineStage(stage="Repository Context Retrieved", duration_ms=120),
                TimelineStage(stage="Security", duration_ms=180),
                TimelineStage(stage="API Compatibility", duration_ms=100),
                TimelineStage(stage="Test Coverage", duration_ms=110),
                TimelineStage(stage="Final Decision", duration_ms=130),
            ],
            agent_statuses=[
                AgentStatus(agent="security", label="Security", status="Completed", files_reviewed=3, duration_ms=180),
                AgentStatus(agent="database", label="Database", status="Skipped", files_reviewed=0, duration_ms=0),
                AgentStatus(agent="api", label="API Compatibility", status="Completed", files_reviewed=1, duration_ms=100),
                AgentStatus(agent="tests", label="Test Coverage", status="Completed", files_reviewed=1, duration_ms=110),
                AgentStatus(agent="performance", label="Performance", status="Skipped", files_reviewed=0, duration_ms=0),
            ],
            repository_metadata=RepositoryMetadata(
                default_branch="main",
                technologies=["TypeScript"],
                files_changed_count=9,
            ),
        ),
    ),
    "db-migration": AnalyzeResponse(
        source="demo",
        ai_enabled=True,
        pr=PullRequestData(
            owner="acme",
            repo="billing-platform",
            number=88,
            title="Add nullable refund_reason column and backfill migration",
            body="Adds a refund_reason column to the invoices table and a backfill migration "
            "for historical rows. No application code reads the column yet.",
            author="jyoon",
            url="https://github.com/acme/billing-platform/pull/88",
            created_at="2024-05-20T09:30:00Z",
            mergeable_state="clean",
            mergeable=True,
            state="open",
            repository={
                "owner": "acme",
                "name": "billing-platform",
                "full_name": "acme/billing-platform",
                "description": "Billing and invoicing platform.",
                "primary_language": "Python",
                "stars": 120,
                "topics": ["database", "payments"],
                "default_branch": "main",
            },
            additions=64,
            deletions=2,
            changed_files_count=3,
            labels=["database"],
            commit_messages=["Add refund_reason migration", "Backfill script for existing invoices"],
            files=[
                ChangedFile(filename="migrations/0042_add_refund_reason.sql", status="added", additions=18, deletions=0, changes=18),
                ChangedFile(filename="migrations/backfill_refund_reason.py", status="added", additions=44, deletions=0, changes=44),
                ChangedFile(filename="schema.sql", status="modified", additions=2, deletions=2, changes=4),
            ],
        ),
        heuristics=HeuristicResult(
            score=35,
            tests_touched=False,
            tests_deleted=False,
            migration_touched=True,
            factors=[
                HeuristicFactor(key="migration", label="Database migration detected", triggered=True, weight=35, reason="Matched in migrations/0042_add_refund_reason.sql"),
                HeuristicFactor(key="no_tests", label="No test files touched", triggered=True, weight=15, reason="This PR changes code but doesn't add or modify any tests."),
            ],
        ),
        ai=AIAnalysis(
            overall_risk=RiskLevel.MEDIUM,
            confidence=84,
            summary="A low-risk, additive schema change: a nullable column plus a backfill script. "
            "Nothing in the application reads the new column yet, which limits blast radius.",
            architectural_impact="Backward-compatible schema addition; safe to deploy ahead of the "
            "application code that will eventually read refund_reason.",
            operational_risks=[
                "Backfill script could lock rows on large invoice tables during off-peak backfill",
                "No test verifying the backfill script's idempotency if it's re-run",
            ],
            rollout_strategy="Staged rollout",
            rollout_reason="Ship the migration ahead of any code that depends on it, and monitor backfill "
            "job duration and lock contention on the invoices table before proceeding.",
            rollback_required=False,
            test_coverage_estimate_pct=40,
            suggested_test_areas=["Migration idempotency", "Backfill dry-run on staging snapshot"],
            risk_factors=[
                RiskFactorFlag(key="database", label="Database", passed=False),
                RiskFactorFlag(key="authentication", label="Authentication", passed=True),
                RiskFactorFlag(key="tests", label="Tests", passed=False),
            ],
            file_risks=[
                FileRisk(filename="migrations/backfill_refund_reason.py", risk=RiskLevel.MEDIUM, reason="Untested backfill logic against production data volume."),
                FileRisk(filename="migrations/0042_add_refund_reason.sql", risk=RiskLevel.LOW, reason="Additive, nullable column; low risk on its own."),
            ],
        ),
        report=RiskReport(
            decision="ALLOW",
            risk_score=35,
            confidence=84,
            deployment_strategy="Blue/Green",
            risk_breakdown={"Database": 35, "Tests": 15},
            findings=["Database migration detected", "No test files touched"],
            evidence=[
                "Database migration detected: Matched in migrations/0042_add_refund_reason.sql",
                "migrations/backfill_refund_reason.py: Untested backfill logic against production data volume.",
            ],
            timeline=[
                TimelineStage(stage="Repository Loaded", duration_ms=90),
                TimelineStage(stage="Repository Context Retrieved", duration_ms=60),
                TimelineStage(stage="Database", duration_ms=210),
                TimelineStage(stage="Final Decision", duration_ms=140),
            ],
            agent_statuses=[
                AgentStatus(agent="security", label="Security", status="Skipped", files_reviewed=0, duration_ms=0),
                AgentStatus(agent="database", label="Database", status="Completed", files_reviewed=3, duration_ms=210),
                AgentStatus(agent="api", label="API Compatibility", status="Skipped", files_reviewed=0, duration_ms=0),
                AgentStatus(agent="tests", label="Test Coverage", status="Completed", files_reviewed=0, duration_ms=90),
                AgentStatus(agent="performance", label="Performance", status="Skipped", files_reviewed=0, duration_ms=0),
            ],
            agent_decisions=build_agent_decisions({
                "database_status": {"agent": "database", "label": "Database", "status": "Completed", "files_reviewed": 3, "duration_ms": 210},
                "database_finding": AgentFinding(
                    agent="database", label="Database", applicable=True,
                    files_reviewed=["migrations/0042_add_refund_reason.sql", "migrations/backfill_refund_reason.py", "schema.sql"],
                    findings=["Migration is additive and reversible", "Backfill script has no explicit idempotency guard"],
                    risk_note="Schema change is safe on its own; the backfill script is the main residual risk.",
                    confidence=78,
                ),
                "tests_status": {"agent": "tests", "label": "Test Coverage", "status": "Completed", "files_reviewed": 0, "duration_ms": 90},
                "tests_finding": AgentFinding(
                    agent="tests", label="Test Coverage", applicable=True, files_reviewed=[],
                    findings=["No test verifies backfill idempotency if re-run"],
                    risk_note="No test files were touched despite new migration logic.",
                    confidence=70,
                ),
            }),
            repository_metadata=RepositoryMetadata(
                default_branch="main",
                technologies=["Python"],
                files_changed_count=3,
            ),
            summary="A low-risk, additive schema change: a nullable column plus a backfill script.",
            executive_summary="This PR adds a nullable refund_reason column and a backfill script for "
            "historical invoice rows. The schema change itself is backward compatible and low risk, but the "
            "backfill script lacks an idempotency guard and could contend for row locks on large tables if "
            "re-run. Recommend a Blue/Green rollout so the migration can be validated independently before "
            "any application code depends on the new column.",
            architectural_impact=ArchitecturalImpact(
                affected_subsystems=["Database", "Tests"],
                narrative="Backward-compatible schema addition to the billing-platform invoices table; safe "
                "to deploy ahead of the application code that will eventually read refund_reason.",
            ),
            confidence_explanation=ConfidenceExplanation(
                score=84,
                repository_context_available=False,
                llm_heuristic_agreement=True,
                evidence_completeness="complete",
                narrative="This assessment is based on complete evidence: the database specialist agent "
                "reviewed all three changed files, and the heuristic score and LLM risk assessment agree "
                "this is a medium-risk, well-scoped migration.",
            ),
            deployment_recommendation=DeploymentRecommendation(
                strategy="Blue/Green",
                reason="Ship the migration ahead of any code that depends on it, and monitor backfill job "
                "duration and lock contention on the invoices table before cutting application traffic over.",
                alternatives_considered=[
                    "Standard (too risky — no visibility into backfill lock contention before it runs)",
                    "Canary (insufficient isolation for a schema-level change)",
                ],
                rollback_required=False,
            ),
        ),
    ),
    "docs-refactor": AnalyzeResponse(
        source="demo",
        ai_enabled=True,
        pr=PullRequestData(
            owner="acme",
            repo="developer-portal",
            number=204,
            title="Reorganize onboarding docs into a single getting-started guide",
            body="Pure documentation restructuring, no code changes. Consolidates three "
            "overlapping onboarding pages into one guide with clearer navigation.",
            author="lchen",
            url="https://github.com/acme/developer-portal/pull/204",
            created_at="2024-04-10T15:20:00Z",
            mergeable_state="clean",
            mergeable=True,
            state="open",
            repository={
                "owner": "acme",
                "name": "developer-portal",
                "full_name": "acme/developer-portal",
                "description": "Developer documentation site and onboarding portal.",
                "primary_language": "Markdown",
                "stars": 32,
                "topics": ["docs", "developer-experience"],
                "default_branch": "main",
            },
            additions=210,
            deletions=245,
            changed_files_count=4,
            labels=["documentation"],
            commit_messages=["Merge onboarding pages", "Fix broken internal links"],
            files=[
                ChangedFile(filename="docs/getting-started.md", status="added", additions=180, deletions=0, changes=180),
                ChangedFile(filename="docs/quickstart.md", status="removed", additions=0, deletions=120, changes=120),
                ChangedFile(filename="docs/setup.md", status="removed", additions=0, deletions=125, changes=125),
                ChangedFile(filename="docs/README.md", status="modified", additions=30, deletions=0, changes=30),
            ],
        ),
        heuristics=HeuristicResult(
            score=0,
            tests_touched=False,
            tests_deleted=False,
            migration_touched=False,
            factors=[],
        ),
        ai=AIAnalysis(
            overall_risk=RiskLevel.LOW,
            confidence=97,
            summary="Documentation-only change with no impact on application behavior. Safe to "
            "merge without staged rollout.",
            architectural_impact="None — no source, config, or infrastructure files were touched.",
            operational_risks=["Broken internal links if the redirect map isn't updated"],
            rollout_strategy="Standard merge",
            rollout_reason="No runtime code paths are affected; a normal merge is sufficient.",
            rollback_required=False,
            test_coverage_estimate_pct=None,
            suggested_test_areas=["Link check on the docs site build"],
            risk_factors=[
                RiskFactorFlag(key="authentication", label="Authentication", passed=True),
                RiskFactorFlag(key="configuration", label="Configuration", passed=True),
                RiskFactorFlag(key="infrastructure", label="Infrastructure", passed=True),
            ],
            file_risks=[
                FileRisk(filename="docs/README.md", risk=RiskLevel.LOW, reason="Navigation links updated; verify none are stale."),
            ],
        ),
        report=RiskReport(
            decision="ALLOW",
            risk_score=0,
            confidence=97,
            deployment_strategy="Standard",
            risk_breakdown={
                "General": 0,
            },
            findings=[
                "Documentation-only change",
            ],
            evidence=[
                "No source, config, or infrastructure files were touched.",
            ],
            timeline=[
                TimelineStage(stage="Repository Loaded", duration_ms=20),
                TimelineStage(stage="Repository Context Retrieved", duration_ms=45),
                TimelineStage(stage="Final Decision", duration_ms=70),
            ],
            agent_statuses=[
                AgentStatus(agent="security", label="Security", status="Skipped", files_reviewed=0, duration_ms=0),
                AgentStatus(agent="database", label="Database", status="Skipped", files_reviewed=0, duration_ms=0),
                AgentStatus(agent="api", label="API Compatibility", status="Skipped", files_reviewed=0, duration_ms=0),
                AgentStatus(agent="tests", label="Test Coverage", status="Skipped", files_reviewed=0, duration_ms=0),
                AgentStatus(agent="performance", label="Performance", status="Skipped", files_reviewed=0, duration_ms=0),
            ],
            repository_metadata=RepositoryMetadata(
                default_branch="main",
                technologies=["Markdown"],
                files_changed_count=4,
            ),
            summary="Documentation-only change with no impact on application behavior.",
            executive_summary="This PR is a pure documentation restructuring with no source, config, or "
            "infrastructure changes. It carries no production risk and is safe to merge without a staged rollout.",
            architectural_impact=ArchitecturalImpact(
                affected_subsystems=["Documentation"],
                narrative="None — no source, config, or infrastructure files were touched.",
            ),
            confidence_explanation=ConfidenceExplanation(
                score=97,
                repository_context_available=False,
                llm_heuristic_agreement=True,
                evidence_completeness="complete",
                narrative="This assessment is based on complete evidence: the change touches only "
                "documentation files, and the heuristic score and LLM risk assessment agree there is no "
                "production risk.",
            ),
            deployment_recommendation=DeploymentRecommendation(
                strategy="Standard",
                reason="No runtime code paths are affected; a normal merge is sufficient.",
                alternatives_considered=[
                    "Canary (unnecessary — no code path is affected)",
                    "Manual Approval (unnecessary overhead for a docs-only change)",
                ],
                rollback_required=False,
            ),
        ),
    ),
}


def list_demos() -> list[DemoSummary]:
    taglines = {
        "auth-refactor": "High-risk: auth rewrite with deleted tests",
        "db-migration": "Medium-risk: additive schema migration",
        "docs-refactor": "Low-risk: documentation-only change",
    }
    return [
        DemoSummary(
            id=demo_id,
            title=resp.pr.title,
            repo=f"{resp.pr.owner}/{resp.pr.repo}",
            pr_number=resp.pr.number,
            tagline=taglines[demo_id],
        )
        for demo_id, resp in DEMOS.items()
    ]


def get_demo(demo_id: str) -> AnalyzeResponse | None:
    return DEMOS.get(demo_id)
