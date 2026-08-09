from __future__ import annotations

from engine.demo_data import DEMOS, get_demo, list_demos
from engine.models import AnalyzeResponse


def test_demos_module_imports_and_is_nonempty():
    """DEMOS must be constructable at import time (all RiskReport payloads valid)."""
    assert len(DEMOS) > 0


def test_every_demo_loads_and_validates():
    """Every demo id must load via get_demo() and produce a valid, enriched AnalyzeResponse."""
    for demo_id in DEMOS:
        response = get_demo(demo_id)
        assert response is not None, f"demo {demo_id!r} failed to load"
        assert isinstance(response, AnalyzeResponse)
        # Deterministic policy fields must be populated by enrich_analyze_response().
        assert response.report.risk_score is not None
        assert response.report.decision in {"ALLOW", "NEEDS_REVIEW", "BLOCK"}
        assert response.report.repository_metadata is not None


def test_get_demo_unknown_id_returns_none():
    assert get_demo("does-not-exist") is None


def test_list_demos_matches_demos_dict():
    summaries = list_demos()
    assert {s.id for s in summaries} == set(DEMOS.keys())
