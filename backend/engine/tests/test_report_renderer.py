from __future__ import annotations

from engine.demo_data import get_demo
from engine.models import JudgeVerdict, ReviewQueueItem, ScoreMathFactor
from engine.report_renderer import render_markdown

# Fixtures are derived from the existing (enriched) demo payloads rather than
# hand-built from scratch, so these tests exercise the same shapes the app
# actually serves and stay in sync with the current renderer contract.
ALLOW_DEMO = get_demo("docs-refactor")
NEEDS_REVIEW_DEMO = get_demo("db-migration")
BLOCK_DEMO = get_demo("auth-refactor")
DISAGREEMENT_DEMO = get_demo("llm-disagreement")


def test_allow_report_renders_successfully():
    assert ALLOW_DEMO.report.decision == "ALLOW"
    markdown = render_markdown(ALLOW_DEMO)
    assert "# PR Sentinel" in markdown
    assert "ALLOW" in markdown


def test_needs_review_report_renders_successfully():
    assert NEEDS_REVIEW_DEMO.report.decision == "NEEDS_REVIEW"
    markdown = render_markdown(NEEDS_REVIEW_DEMO)
    assert "NEEDS_REVIEW" in markdown


def test_block_report_renders_successfully():
    assert BLOCK_DEMO.report.decision == "BLOCK"
    markdown = render_markdown(BLOCK_DEMO)
    assert "BLOCK" in markdown


def test_llm_disagreement_section_rendered_when_disagreement_exists():
    assert DISAGREEMENT_DEMO.report.llm_disagreement is not None
    assert DISAGREEMENT_DEMO.report.llm_disagreement.detected is True
    markdown = render_markdown(DISAGREEMENT_DEMO)
    assert "Deterministic Override" in markdown
    assert "LLM Disagreement Audit" in markdown


def test_llm_disagreement_section_absent_when_no_disagreement():
    assert ALLOW_DEMO.report.llm_disagreement is None or not ALLOW_DEMO.report.llm_disagreement.detected
    markdown = render_markdown(ALLOW_DEMO)
    assert "Deterministic Override" not in markdown


def test_groundedness_failure_warning_rendered_when_judge_not_grounded():
    response = ALLOW_DEMO.model_copy(
        update={"judge": JudgeVerdict(grounded=False, issues=["Unsupported claim about rollout strategy."])}
    )
    markdown = render_markdown(response)
    assert "Evidence requires review" in markdown
    assert "Unsupported claim about rollout strategy." in markdown
    # The release decision must remain framed as deterministic, not overridden by the judge.
    assert "release decision above is unaffected" in markdown


def test_no_groundedness_warning_when_judge_passes():
    response = ALLOW_DEMO.model_copy(update={"judge": JudgeVerdict(grounded=True)})
    markdown = render_markdown(response)
    assert "Evidence requires review" not in markdown


def test_review_queue_section_rendered_when_queue_items_exist():
    queue_item = ReviewQueueItem(
        priority="P1",
        filename="auth/session_store.ts",
        role="Removed with no equivalent test coverage",
        why_it_matters="Session handling regressions would be undetected.",
        potential_regression="Silent auth bypass",
        suggested_validation="Add integration test covering token refresh",
        estimated_minutes=20,
    )
    response = BLOCK_DEMO.model_copy(update={"report": BLOCK_DEMO.report.model_copy(update={"review_queue": [queue_item]})})
    markdown = render_markdown(response)
    assert "## Review Queue" in markdown
    assert "auth/session_store.ts" in markdown


def test_no_review_queue_section_when_queue_empty():
    response = BLOCK_DEMO.model_copy(update={"report": BLOCK_DEMO.report.model_copy(update={"review_queue": []})})
    markdown = render_markdown(response)
    assert "## Review Queue" not in markdown


def test_release_risk_calculation_contains_deterministic_score():
    score_math = [ScoreMathFactor(factor="Authentication logic touched", points=40, reason="Matched in auth/middleware.ts")]
    response = BLOCK_DEMO.model_copy(update={"report": BLOCK_DEMO.report.model_copy(update={"score_math": score_math})})
    markdown = render_markdown(response)
    assert "### Release Risk Calculation" in markdown
    assert f"`{response.report.risk_score}`" in markdown


def test_renderer_does_not_claim_llm_controls_release_decision():
    for demo in (ALLOW_DEMO, NEEDS_REVIEW_DEMO, BLOCK_DEMO, DISAGREEMENT_DEMO):
        markdown = render_markdown(demo)
        assert "deterministic policy controls release decisions" in markdown
        # Guard against future regressions that hand the decision to the LLM.
        assert "LLM decides" not in markdown
        assert "LLM controls the release" not in markdown
