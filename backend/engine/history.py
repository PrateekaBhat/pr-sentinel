"""Historical Repository Intelligence.

Every completed analysis is persisted to a local SQLite file so a team can see
trends across PRs instead of only ever looking at one report in isolation.
This is deliberately a single flat table with a JSON blob for the
harder-to-normalize bits (agent decisions, categories triggered) — the goal is
"an engineering team can query their own risk history", not a full data
warehouse.

Read path (`get_history`, `get_repository_health`) is what the `/api/history`
and `/api/repository-health` endpoints in app/main.py call.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import get_settings
from .models import AnalyzeResponse

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    pr_title TEXT NOT NULL,
    author TEXT NOT NULL,
    analyzed_at TEXT NOT NULL,
    decision TEXT NOT NULL,
    overall_risk TEXT NOT NULL,
    risk_score INTEGER NOT NULL,
    confidence INTEGER NOT NULL,
    deployment_recommendation TEXT NOT NULL,
    total_duration_ms INTEGER NOT NULL,
    files_changed INTEGER NOT NULL,
    additions INTEGER NOT NULL,
    deletions INTEGER NOT NULL,
    heuristic_score INTEGER NOT NULL,
    categories_triggered TEXT NOT NULL,     -- JSON list[str]
    agent_decisions TEXT NOT NULL,          -- JSON list[dict]
    human_decision TEXT,                    -- Feature 13 hook: null until overridden
    human_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_analyses_repository ON analyses(repository);
CREATE INDEX IF NOT EXISTS idx_analyses_analyzed_at ON analyses(analyzed_at);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    settings = get_settings()
    conn = sqlite3.connect(settings.history_db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def record_analysis(response: AnalyzeResponse) -> None:
    """Persist a completed analysis. Best-effort: a history-write failure must
    never take down the analysis endpoint, so callers should wrap this in a
    try/except (see service.py)."""
    pr = response.pr
    report = response.report
    categories_triggered = [c.category for c in report.risk_categories if c.evidence]
    agent_decisions = [
        {
            "agent": d.agent,
            "label": d.label,
            "decision": d.decision,
            "confidence": d.confidence,
            "execution_time_ms": d.execution_time_ms,
        }
        for d in report.agent_decisions
    ]

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO analyses (
                repository, pr_number, pr_title, author, analyzed_at,
                decision, overall_risk, risk_score, confidence,
                deployment_recommendation, total_duration_ms,
                files_changed, additions, deletions, heuristic_score,
                categories_triggered, agent_decisions
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pr.repository.full_name,
                pr.number,
                pr.title,
                pr.author,
                datetime.now(timezone.utc).isoformat(),
                report.decision,
                response.ai.overall_risk.value if hasattr(response.ai.overall_risk, "value") else str(response.ai.overall_risk),
                report.risk_score,
                report.confidence,
                report.deployment_strategy,
                report.execution_metrics.total_duration_ms if report.execution_metrics else 0,
                pr.changed_files_count,
                pr.additions,
                pr.deletions,
                response.heuristics.score,
                json.dumps(categories_triggered),
                json.dumps(agent_decisions),
            ),
        )


def get_history(limit: int = 50, repository: str | None = None) -> list[dict[str, Any]]:
    """Latest analyses, newest first."""
    with _connect() as conn:
        if repository:
            rows = conn.execute(
                "SELECT * FROM analyses WHERE repository = ? ORDER BY analyzed_at DESC LIMIT ?",
                (repository, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM analyses ORDER BY analyzed_at DESC LIMIT ?", (limit,)
            ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        item["categories_triggered"] = json.loads(item["categories_triggered"])
        item["agent_decisions"] = json.loads(item["agent_decisions"])
        results.append(item)
    return results


def get_repository_health(repository: str | None = None, window: int = 100) -> dict[str, Any]:
    """Aggregate stats over the most recent `window` analyses (optionally
    scoped to one repository). Powers the dashboard's Repository Health panel."""
    rows = get_history(limit=window, repository=repository)
    if not rows:
        return {
            "repository": repository,
            "analyses_count": 0,
            "average_risk_score": 0,
            "average_confidence": 0,
            "average_files_changed": 0,
            "average_review_duration_ms": 0,
            "deployment_distribution": {},
            "top_recurring_categories": [],
            "risk_trend": [],
            "decision_trend": [],
        }

    n = len(rows)
    avg_risk = round(sum(r["risk_score"] for r in rows) / n, 1)
    avg_confidence = round(sum(r["confidence"] for r in rows) / n, 1)
    avg_files = round(sum(r["files_changed"] for r in rows) / n, 1)
    avg_duration = round(sum(r["total_duration_ms"] for r in rows) / n)

    deployment_counts = Counter(r["deployment_recommendation"] for r in rows)
    category_counts: Counter[str] = Counter()
    for r in rows:
        category_counts.update(r["categories_triggered"])

    # Trends returned oldest -> newest so a chart can plot left-to-right directly.
    chronological = list(reversed(rows))
    risk_trend = [
        {"analyzed_at": r["analyzed_at"], "pr_number": r["pr_number"], "risk_score": r["risk_score"]}
        for r in chronological
    ]
    decision_trend = [
        {"analyzed_at": r["analyzed_at"], "pr_number": r["pr_number"], "decision": r["decision"]}
        for r in chronological
    ]

    return {
        "repository": repository,
        "analyses_count": n,
        "average_risk_score": avg_risk,
        "average_confidence": avg_confidence,
        "average_files_changed": avg_files,
        "average_review_duration_ms": avg_duration,
        "deployment_distribution": dict(deployment_counts),
        "top_recurring_categories": category_counts.most_common(5),
        "risk_trend": risk_trend,
        "decision_trend": decision_trend,
    }


def set_human_decision(analysis_id: int, decision: str, reason: str = "") -> bool:
    """Feature 13 hook (manual override), left minimal and unwired from the API
    for now — the storage and read path exist so this can be turned on without
    a schema migration once the review-override UX is actually designed."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE analyses SET human_decision = ?, human_reason = ? WHERE id = ?",
            (decision, reason, analysis_id),
        )
        return cur.rowcount > 0
