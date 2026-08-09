"""Deterministic regression tests for the HTTP API contract.

These exist because an LLM-based reviewer has previously hallucinated claims
about this contract (e.g. "renamed /api/analyze to fetchHistory", which never
happened). Route existence/shape and the frontend client's URLs must be
verified mechanically, not asserted by an LLM.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

FRONTEND_CLIENT = (
    Path(__file__).resolve().parents[3] / "frontend" / "src" / "api" / "client.ts"
)

client = TestClient(app)


# --- Backend route inventory -------------------------------------------------

EXPECTED_ROUTES = {
    ("POST", "/api/analyze"),
    ("GET", "/api/history"),
    ("GET", "/api/golden-tests"),
    ("GET", "/api/repository-health"),
    ("GET", "/api/demos"),
    ("GET", "/api/demos/{demo_id}"),
    ("GET", "/api/health"),
}


def _actual_routes() -> set[tuple[str, str]]:
    routes = set()
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path or not path.startswith("/api"):
            continue
        for method in methods:
            if method == "HEAD":
                continue
            routes.add((method, path))
    return routes


def test_backend_exposes_the_documented_api_contract():
    """Every documented endpoint must exist on the running FastAPI app."""
    actual = _actual_routes()
    missing = EXPECTED_ROUTES - actual
    assert not missing, f"Documented endpoints missing from backend: {missing}"


def test_backend_has_not_silently_grown_undocumented_api_routes():
    """Guard against silent contract drift: new /api routes should be
    intentional and reflected in EXPECTED_ROUTES, not accidental."""
    actual = _actual_routes()
    extra = actual - EXPECTED_ROUTES
    assert not extra, f"Undocumented /api routes found: {extra}. Update this test if intentional."


# --- Frontend client mapping (regex-based, deterministic) -------------------

@pytest.fixture(scope="module")
def frontend_client_source() -> str:
    if not FRONTEND_CLIENT.exists():
        pytest.skip(f"frontend client not found at {FRONTEND_CLIENT}")
    return FRONTEND_CLIENT.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "function_name, expected_path",
    [
        ("analyzePullRequest", "/api/analyze"),
        ("fetchHistory", "/api/history"),
        ("fetchGoldenTests", "/api/golden-tests"),
        ("fetchRepositoryHealth", "/api/repository-health"),
        ("fetchDemos", "/api/demos"),
    ],
)
def test_frontend_function_calls_expected_endpoint(frontend_client_source, function_name, expected_path):
    """Each named client function must reference its documented endpoint
    path somewhere in its own body (not just anywhere in the file)."""
    match = re.search(
        rf"export\s+async\s+function\s+{re.escape(function_name)}\s*\([^)]*\)[^{{]*\{{(.*?)\n\}}",
        frontend_client_source,
        re.DOTALL,
    )
    assert match, f"Could not find function {function_name}() in {FRONTEND_CLIENT}"
    body = match.group(1)
    assert expected_path in body, (
        f"{function_name}() does not reference {expected_path} in its body; "
        "the API contract may have drifted."
    )


def test_frontend_does_not_reference_undocumented_endpoints(frontend_client_source):
    """Every /api/... literal referenced by the frontend must be one of the
    documented endpoints (allowing the /api/demos/{id} path param)."""
    referenced = set(re.findall(r"/api/[a-zA-Z0-9\-_/${}]*", frontend_client_source))
    documented_prefixes = {path.split("{")[0] for _, path in EXPECTED_ROUTES}
    for ref in referenced:
        base = ref.split("?")[0].split("$")[0]
        assert any(base.startswith(prefix) for prefix in documented_prefixes), (
            f"Frontend references undocumented endpoint: {ref}"
        )
