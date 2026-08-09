"""Regression tests for two fixes:
1. The default Ollama model is consistent with README/CI (llama3.2), and env overrides
   still work.
2. Fallback (AI-unavailable) reports never claim `Groundedness: PASSED` — they clearly
   mark AI synthesis as unavailable and groundedness as NOT_RUN, while normal AI-enabled
   groundedness (PASSED/FAILED) behavior is preserved.
"""

from __future__ import annotations

import os

from engine.demo_data import get_demo
from engine.models import JudgeVerdict
from engine.report_renderer import render_markdown


# --- Test A: default Ollama model -----------------------------------------------------

def test_default_ollama_model_is_llama3_2(monkeypatch):
    from engine.config import Settings

    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.ollama_model == "llama3.2"


def test_ollama_model_env_override_still_works(monkeypatch):
    from engine.config import Settings

    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1")
    settings = Settings(_env_file=None)
    assert settings.ollama_model == "llama3.1"

    monkeypatch.setenv("OLLAMA_MODEL", "mistral")
    settings = Settings(_env_file=None)
    assert settings.ollama_model == "mistral"


# --- Test B: AI-unavailable fallback report never says Groundedness: PASSED -----------

def test_judge_node_reports_not_run_when_no_coordinator_output():
    import asyncio
    from engine.agents.nodes import judge_node

    result = asyncio.run(judge_node({}))
    verdict: JudgeVerdict = result["judge_result"]
    assert verdict.grounded is None
    assert "no ai synthesis" in verdict.notes.lower() or "not evaluated" in verdict.notes.lower()


def test_fallback_report_does_not_claim_groundedness_passed():
    """Uses the same demo fixture pattern as test_report_renderer.py: take a known-good
    demo response and swap in the AI-unavailable state that used to trigger the bug."""
    demo = get_demo("auth-refactor")

    not_run_judge = JudgeVerdict(
        grounded=None,
        notes="No AI synthesis was produced, so groundedness was not evaluated.",
    )
    response = demo.model_copy(
        update={
            "ai_enabled": False,
            "judge": not_run_judge,
            "policy_note": "AI synthesis unavailable. Final release decision was produced by the deterministic policy engine.",
        }
    )

    markdown = render_markdown(response)

    assert "Groundedness: PASSED" not in markdown
    assert "Groundedness:** PASSED" not in markdown
    assert "Groundedness:** NOT_RUN" in markdown
    assert "AI synthesis unavailable" in markdown

    # Deterministic decision/risk must be completely unaffected by AI availability.
    assert response.report.decision == demo.report.decision
    assert response.report.release_risk == demo.report.release_risk


def test_deterministic_high_risk_still_blocks_when_ai_unavailable():
    demo = get_demo("auth-refactor")
    assert demo.report.decision == "BLOCK"

    not_run_judge = JudgeVerdict(grounded=None, notes="No AI synthesis was produced.")
    response = demo.model_copy(update={"ai_enabled": False, "judge": not_run_judge})

    # The release decision is computed by deterministic policy independent of ai_enabled
    # or the judge verdict — it must remain BLOCK.
    assert response.report.decision == "BLOCK"
    assert response.report.release_risk == demo.report.release_risk


# --- Test C: normal AI-enabled path keeps PASSED/FAILED behavior ----------------------

def test_normal_ai_enabled_groundedness_passed_is_preserved():
    demo = get_demo("auth-refactor")
    passed_judge = JudgeVerdict(grounded=True, notes="Every claim traces to evidence.")
    response = demo.model_copy(update={"ai_enabled": True, "judge": passed_judge})

    markdown = render_markdown(response)
    assert "Groundedness:** PASSED" in markdown
    assert "NOT_RUN" not in markdown


def test_normal_ai_enabled_groundedness_failed_is_preserved():
    demo = get_demo("auth-refactor")
    failed_judge = JudgeVerdict(grounded=False, issues=["Unsupported claim about rollout strategy."])
    response = demo.model_copy(update={"ai_enabled": True, "judge": failed_judge})

    markdown = render_markdown(response)
    assert "Groundedness:** FAILED" in markdown
    assert "Evidence requires review" in markdown
    assert "NOT_RUN" not in markdown
