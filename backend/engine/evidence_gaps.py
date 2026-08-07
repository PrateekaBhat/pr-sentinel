from __future__ import annotations

from .agent_routing import files_for_domain
from .models import (
    AIAnalysis,
    HeuristicResult,
    PositiveSignal,
    PullRequestData,
    RAGContext,
    RiskCategory,
    UncertaintyItem,
)

# Rule keys from heuristics.PATH_RULES that are worth surfacing as reassurance
# when they did NOT trigger. Kept as an explicit allowlist (rather than "every
# untriggered rule") so trivial/noisy rules don't dilute the signal.
_REASSURING_KEYS = {"auth", "payment", "config", "migration", "api_contract", "infra"}


def build_positive_signals(heuristics: HeuristicResult) -> list[PositiveSignal]:
    """Surfaces the mirror image of the risk factors: what did NOT change,
    backed by the same rule engine that computes the risk score. This is what
    lets a LOW-risk verdict say *why* it's low instead of just not being HIGH.
    """
    signals: list[PositiveSignal] = []

    for factor in heuristics.factors:
        if factor.triggered or factor.key not in _REASSURING_KEYS:
            continue
        label = factor.label[0].upper() + factor.label[1:]
        signals.append(
            PositiveSignal(
                label=f"No {label[0].lower()}{label[1:]}",
                reason="No files in this diff matched this pattern.",
            )
        )

    if not heuristics.tests_deleted:
        signals.append(
            PositiveSignal(
                label="No test files were deleted",
                reason="Existing test coverage was left intact.",
            )
        )

    if heuristics.tests_touched:
        signals.append(
            PositiveSignal(
                label="Tests were added or modified alongside the change",
                reason="Code changes in this PR are accompanied by test changes.",
            )
        )

    return signals


def build_uncertainties(
    pr: PullRequestData,
    heuristics: HeuristicResult,
    ai: AIAnalysis,
    rag: RAGContext,
    categories: list[RiskCategory],
) -> list[UncertaintyItem]:
    """Explicitly names what PR Sentinel could NOT determine, instead of
    silently omitting it or letting the LLM guess with false confidence. Each
    item traces to a concrete absence of evidence (missing file category,
    missing repo docs, missing coverage tooling) rather than a vague caveat.
    """
    items: list[UncertaintyItem] = []
    by_category = {c.category: c for c in categories}

    if not rag.scanned:
        items.append(
            UncertaintyItem(
                area="Repository documentation context",
                reason=rag.skip_reason or "Repository documentation could not be indexed for this analysis.",
            )
        )

    if ai.test_coverage_estimate_pct is None:
        items.append(
            UncertaintyItem(
                area="Test coverage impact",
                reason="No coverage tooling output is available; only the presence of test files was checked, "
                "not actual line/branch coverage.",
            )
        )

    data_layer = by_category.get("Data Layer")
    if heuristics.migration_touched or (data_layer and data_layer.evidence):
        items.append(
            UncertaintyItem(
                area="Migration backward-compatibility",
                reason="No rollback/down-migration script or backward-compatibility test was detected in this "
                "diff -- whether this migration is safely reversible cannot be automatically determined.",
            )
        )

    perf_relevant_categories = [by_category.get(c) for c in ("Data Layer", "Infrastructure", "API")]
    touches_perf_relevant = any(c and c.evidence for c in perf_relevant_categories)
    perf_files = files_for_domain(pr.files, "performance")
    if touches_perf_relevant and not perf_files:
        items.append(
            UncertaintyItem(
                area="Performance impact",
                reason="This PR touches infrastructure, data-layer, or API code, but no benchmark, cache, "
                "queue, or index-related files were changed to validate performance impact.",
            )
        )

    secrets_cat = by_category.get("Secrets")
    if not secrets_cat or not secrets_cat.evidence:
        # Deliberately NOT added as an uncertainty: absence of secrets-pattern
        # matches is a positive signal, not a gap. Left as a comment so a future
        # editor doesn't "fix" this by adding a low-value item here.
        pass

    return items
