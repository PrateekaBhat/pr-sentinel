"""Golden architecture test registry for API / UI demo."""

from __future__ import annotations

from dataclasses import dataclass

from engine.tests import test_golden_architecture as golden


@dataclass
class GoldenTestResult:
    id: str
    name: str
    passed: bool
    expected: str
    actual: str


_CASES: list[tuple[str, str, callable]] = [
    ("Critical Auth Refactor", "auth-refactor", golden.test_critical_auth_refactor),
    ("Database Migration", "db-migration", golden.test_database_migration),
    ("Routine Backend Refactor", "routine-refactor", golden.test_routine_backend_refactor),
    ("Docs Only", "docs-only", golden.test_docs_only),
    ("Large Diff Separation", "large-diff", golden.test_large_diff_separation),
    ("Optimistic LLM Override", "optimistic-llm", golden.test_optimistic_llm_override),
    ("Pessimistic LLM Override", "pessimistic-llm", golden.test_pessimistic_llm_override),
    ("Multi-Domain Routing", "multi-domain", golden.test_multi_domain_routing),
    ("LLM Outage Resilience", "llm-outage", golden.test_llm_outage_resilience),
]


def run_golden_tests() -> list[GoldenTestResult]:
    results: list[GoldenTestResult] = []
    for name, test_id, fn in _CASES:
        try:
            fn()
            results.append(GoldenTestResult(id=test_id, name=name, passed=True, expected="pass", actual="pass"))
        except AssertionError as exc:
            results.append(
                GoldenTestResult(
                    id=test_id,
                    name=name,
                    passed=False,
                    expected="pass",
                    actual=str(exc) or "assertion failed",
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                GoldenTestResult(id=test_id, name=name, passed=False, expected="pass", actual=str(exc))
            )
    return results
