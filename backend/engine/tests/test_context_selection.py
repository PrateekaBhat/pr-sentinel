"""Tests for the trimmed context-selection improvements:
1. Relevance ranking within already domain-matched files.
2. Context limits (MAX_FILES_PER_AGENT / MAX_PATCH_LINES / MAX_PATCH_CHARS) are
   configurable via Settings / env vars, with today's defaults preserved.
3. Specialist routing reports available/selected/bounded context metadata, and never
   claims a specialist reviewed a file it wasn't actually shown.
4. Existing empty-domain and Ollama-timeout fallback behavior is unchanged.
"""

from __future__ import annotations

import asyncio

from engine import agent_routing
from engine.models import ChangedFile, PullRequestData, RepositoryInfo


def _file(name: str, additions: int = 1, deletions: int = 0, patch: str = "+x") -> ChangedFile:
    return ChangedFile(
        filename=name, status="modified", additions=additions, deletions=deletions,
        changes=additions + deletions, patch=patch,
    )


def _pr(files: list[ChangedFile]) -> PullRequestData:
    return PullRequestData(
        owner="acme", repo="widgets", number=1, title="t", author="a", url="u",
        state="open", additions=sum(f.additions for f in files),
        deletions=sum(f.deletions for f in files), changed_files_count=len(files),
        files=files, repository=RepositoryInfo(owner="acme", name="widgets", full_name="acme/widgets"),
    )


# --- 1. Relevance ranking ---------------------------------------------------------

def test_ranking_prefers_stronger_domain_keyword_match_in_filename():
    files = [
        _file("backend/api/utils.py"),           # weak: only dir-level "api" match
        _file("backend/api/auth_controller.py"),  # strong: "controller" + "auth" in basename
    ]
    domain_files = agent_routing.files_for_domain(files, "api")
    ranked = agent_routing.rank_files_for_domain(domain_files, "api")
    assert ranked[0].filename == "backend/api/auth_controller.py"


def test_ranking_uses_change_size_as_lower_priority_signal():
    files = [
        _file("backend/api/routes_small.py", additions=1, deletions=0),
        _file("backend/api/routes_big.py", additions=50, deletions=10),
    ]
    domain_files = agent_routing.files_for_domain(files, "api")
    ranked = agent_routing.rank_files_for_domain(domain_files, "api")
    # Both have identical keyword strength ("routes" match), so change size breaks the tie.
    assert ranked[0].filename == "backend/api/routes_big.py"


def test_ranking_only_reorders_already_matched_files_does_not_change_membership():
    files = [_file("backend/api/routes.py"), _file("backend/other/thing.py")]
    domain_files = agent_routing.files_for_domain(files, "api")
    ranked = agent_routing.rank_files_for_domain(domain_files, "api")
    assert {f.filename for f in ranked} == {f.filename for f in domain_files}
    assert len(ranked) == 1


# --- 2. Configurable context limits -------------------------------------------------

def test_context_limit_defaults_match_previous_hardcoded_values(monkeypatch):
    from engine.config import Settings

    monkeypatch.delenv("MAX_FILES_PER_AGENT", raising=False)
    monkeypatch.delenv("MAX_PATCH_LINES", raising=False)
    monkeypatch.delenv("MAX_PATCH_CHARS", raising=False)
    settings = Settings(_env_file=None)
    assert settings.max_files_per_agent == 4
    assert settings.max_patch_lines == 30
    assert settings.max_patch_chars == 600


def test_context_limit_env_override_works():
    from engine.config import Settings

    settings = Settings(_env_file=None, max_files_per_agent=7, max_patch_lines=99, max_patch_chars=1234)
    assert settings.max_files_per_agent == 7
    assert settings.max_patch_lines == 99
    assert settings.max_patch_chars == 1234


# --- 3. Context metadata -------------------------------------------------------------

def test_specialist_routing_reports_available_selected_and_bounded():
    from engine.categories import build_specialist_routing
    from engine.models import AgentFinding

    files = [_file(f"backend/api/routes_{i}.py") for i in range(6)]
    pr = _pr(files)
    finding = AgentFinding(
        agent="api", label="API Compatibility", applicable=True,
        files_reviewed=[f.filename for f in files[:4]], findings=[],
    )
    state = {
        "api_finding": finding,
        "api_status": {
            "agent": "api", "label": "API Compatibility", "status": "Completed",
            "files_reviewed": 4, "duration_ms": 1200, "files_available": 6,
            "context_bounded": True,
        },
    }
    routing = build_specialist_routing(state, pr)
    entry = next(e for e in routing if e.domain == "api")
    assert entry.files_available == 6
    assert entry.files_selected == 4
    assert entry.context_bounded is True


def test_specialist_routing_never_claims_more_files_reviewed_than_shown():
    """Regression: files_reviewed on the AgentFinding (and therefore the routing entry)
    must only ever list files that were actually sent to the LLM, never every
    domain-matched file."""
    from engine.categories import build_specialist_routing
    from engine.models import AgentFinding

    files = [_file(f"backend/api/routes_{i}.py") for i in range(6)]
    pr = _pr(files)
    finding = AgentFinding(
        agent="api", label="API Compatibility", applicable=True,
        files_reviewed=[f.filename for f in files[:4]], findings=[],
    )
    state = {
        "api_finding": finding,
        "api_status": {
            "agent": "api", "label": "API Compatibility", "status": "Completed",
            "files_reviewed": 4, "duration_ms": 1200, "files_available": 6,
            "context_bounded": True,
        },
    }
    routing = build_specialist_routing(state, pr)
    entry = next(e for e in routing if e.domain == "api")
    assert entry.files_count == len(finding.files_reviewed)
    assert set(entry.files).issubset(set(finding.files_reviewed))


# --- 5. Existing empty-domain behavior is unchanged ----------------------------------

def test_empty_domain_still_skips_llm_call():
    from engine.agents.nodes import run_agent

    pr = _pr([_file("docs/readme.md")])
    result = asyncio.run(run_agent("security", {"pr": pr}))
    finding = result["security_finding"]
    assert finding.applicable is False
    assert finding.files_reviewed == []
    assert result["security_status"]["status"] == "Skipped"


# --- 6. Existing Ollama timeout fallback is unchanged ---------------------------------

def test_ollama_timeout_fallback_still_produces_no_fabricated_findings(monkeypatch):
    from engine.agents import nodes
    from engine.ollama_client import OllamaError

    async def _boom(*args, **kwargs):
        raise OllamaError("Ollama timed out.")

    monkeypatch.setattr(nodes, "chat_json", _boom)

    pr = _pr([_file("backend/api/routes.py")])
    result = asyncio.run(nodes.run_agent("api", {"pr": pr}))
    finding = result["api_finding"]
    assert finding.applicable is True
    assert finding.findings == []
    assert finding.structured_findings == []
    assert finding.confidence == 0
    assert "Agent call failed" in finding.risk_note
