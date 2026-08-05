"""Curated demo PRs.

These are synthetic (not fetched from real repos) so the gallery is fast, free, and
deterministic to demo, while the app still supports analyzing any real public PR by URL
via /api/analyze. Each entry is a fully-formed AnalyzeResponse payload.
"""
from __future__ import annotations

from .models import (
    AIAnalysis,
    AnalyzeResponse,
    ChangedFile,
    DemoSummary,
    FileRisk,
    HeuristicFactor,
    HeuristicResult,
    PullRequestData,
    RiskFactorFlag,
    RiskLevel,
)

DEMOS: dict[str, AnalyzeResponse] = {
    "auth-refactor": AnalyzeResponse(
        source="demo",
        ai_enabled=True,
        pr=PullRequestData(
            owner="acme",
            repo="orders-service",
            number=421,
            title="Migrate session validation to PingFederate JWT introspection",
            body="Replaces the legacy session-cookie auth middleware with JWT introspection "
            "against PingFederate. Removes the old `SessionStore` and its tests.",
            author="rpatel",
            url="https://github.com/acme/orders-service/pull/421",
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
