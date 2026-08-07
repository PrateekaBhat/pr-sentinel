from __future__ import annotations

import os
import tempfile

import pytest

from engine.config import get_settings
from engine.demo_data import DEMOS


@pytest.fixture()
def temp_history_db(monkeypatch):
    """Point history at a throwaway SQLite file for the duration of the test,
    and clear the cached settings singleton so the new path takes effect."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # let sqlite create it fresh
    monkeypatch.setenv("HISTORY_DB_PATH", path)
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()
    if os.path.exists(path):
        os.remove(path)


def test_record_and_read_history(temp_history_db):
    from engine import history

    demo = list(DEMOS.values())[0]
    history.record_analysis(demo)
    history.record_analysis(demo)

    rows = history.get_history(limit=10)
    assert len(rows) == 2
    assert rows[0]["repository"] == demo.pr.repository.full_name
    assert rows[0]["pr_number"] == demo.pr.number


def test_repository_health_aggregation(temp_history_db):
    from engine import history

    demo = list(DEMOS.values())[0]
    history.record_analysis(demo)
    history.record_analysis(demo)
    history.record_analysis(demo)

    health = history.get_repository_health()
    assert health["analyses_count"] == 3
    assert health["average_risk_score"] == demo.report.risk_score
    assert len(health["risk_trend"]) == 3
    assert len(health["decision_trend"]) == 3


def test_repository_health_empty_is_safe(temp_history_db):
    from engine import history

    health = history.get_repository_health()
    assert health["analyses_count"] == 0
    assert health["risk_trend"] == []
