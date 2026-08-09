from __future__ import annotations

from engine import finding_validation
from engine.categories import build_agent_decisions
from engine.models import AgentDecision, AgentFinding, ReleaseDecision, RiskLevel
from engine.policy import audit_llm_disagreement, decide_release, evaluate_policy


# --- TEST 1: malformed specialist finding is never rendered as an actionable claim ----

def test_truncated_finding_is_rejected_not_rendered():
    raw = {"title": "function exists with different return type than"}
    finding = finding_validation.normalize_finding(raw)
    assert finding is None


def test_truncated_legacy_string_finding_is_rejected():
    actionable, needs_verification, rejected = finding_validation.normalize_findings(
        ["function exists with different return type than"]
    )
    assert actionable == []
    assert needs_verification == []
    assert rejected == 1


# --- TEST 2: a valid structured API compatibility finding renders correctly -----------

def test_valid_structured_finding_is_accepted():
    raw = {
        "title": "API return type changed for fetchHistory",
        "file": "backend/app/ai_analyzer.py",
        "evidence": "The function return annotation changed from list[dict] to AIAnalysis.",
        "impact": "Existing callers expecting the previous response contract may break.",
        "recommendation": "Add an API compatibility test for fetchHistory callers.",
        "severity": "P2",
        "confidence": "HIGH",
    }
    finding = finding_validation.normalize_finding(raw)
    assert finding is not None
    assert finding.title == raw["title"]
    assert finding.severity == "P2"
    assert finding.confidence == "HIGH"


def test_valid_findings_are_never_truncated_in_agent_decision_reasoning():
    long_title = "API return type changed for fetchHistory across the public client contract"
    finding = AgentFinding(
        agent="api",
        label="API Compatibility",
        applicable=True,
        files_reviewed=["backend/app/ai_analyzer.py"],
        findings=[long_title],
        structured_findings=[
            finding_validation.normalize_finding(
                {
                    "title": long_title,
                    "evidence": "Return annotation changed in ai_analyzer.py.",
                    "severity": "P2",
                    "confidence": "HIGH",
                }
            )
        ],
        confidence=80,
    )
    state = {
        "api_finding": finding,
        "api_status": {"agent": "api", "label": "API Compatibility", "status": "Completed", "files_reviewed": 1, "duration_ms": 10},
    }
    decisions = build_agent_decisions(state)
    assert len(decisions) == 1
    assert long_title in decisions[0].reasoning
    assert not decisions[0].reasoning.endswith("than")


# --- TEST 3: a weak Test Coverage observation does not automatically become a P2 concern

def test_weak_test_coverage_observation_without_evidence_is_discarded():
    raw = {"title": "No test for empty DEMOS list"}  # no evidence supplied
    finding = finding_validation.normalize_finding(raw)
    assert finding is None


def test_low_confidence_test_coverage_observation_is_needs_verification_not_a_concern():
    raw = {
        "title": "Empty DEMOS registry may be an unhandled runtime state",
        "evidence": "demo_data.py asserts DEMOS is non-empty but no test covers an empty registry.",
        "confidence": "LOW",
    }
    actionable, needs_verification, rejected = finding_validation.normalize_findings([raw])
    assert actionable == []
    assert len(needs_verification) == 1
    assert rejected == 0


# --- TEST 4: a genuine missing behavioral test can still become a concern -------------

def test_genuine_missing_behavioral_test_finding_is_actionable():
    raw = {
        "title": "New retry logic in review_queue.py has no test coverage",
        "file": "backend/engine/review_queue.py",
        "evidence": "This PR adds a retry loop with exponential backoff but no test file was modified.",
        "impact": "A regression in the retry loop's termination condition would go undetected.",
        "recommendation": "Add a test asserting the retry loop terminates after the max attempt count.",
        "severity": "P1",
        "confidence": "HIGH",
    }
    actionable, needs_verification, rejected = finding_validation.normalize_findings([raw])
    assert len(actionable) == 1
    assert needs_verification == []
    assert rejected == 0


# --- TEST 5: missing evidence causes a finding to be downgraded/rejected --------------

def test_missing_evidence_causes_rejection():
    raw = {"title": "Tests are insufficient for this change"}
    finding = finding_validation.normalize_finding(raw)
    assert finding is None


def test_file_specific_claim_without_evidence_is_rejected():
    raw = {"title": "API compatibility may be broken here", "file": "backend/app/main.py"}
    finding = finding_validation.normalize_finding(raw)
    assert finding is None


# --- TEST 6 & 7: coordinator input preserves uncertainty and does not amplify ---------

def test_coordinator_prompt_carries_severity_and_confidence_per_finding():
    from engine.agents.nodes import _build_coordinator_prompt
    from engine.models import ChangedFile, HeuristicResult, PullRequestData, RepositoryInfo

    pr = PullRequestData(
        owner="acme",
        repo="widgets",
        number=1,
        title="test pr",
        author="octocat",
        url="https://github.com/acme/widgets/pull/1",
        state="open",
        additions=10,
        deletions=2,
        changed_files_count=1,
        files=[ChangedFile(filename="backend/app/main.py", status="modified", additions=10, deletions=2, changes=12)],
        repository=RepositoryInfo(owner="acme", name="widgets", full_name="acme/widgets"),
    )
    heuristics = HeuristicResult(score=10, factors=[], tests_touched=False, tests_deleted=False, migration_touched=False)
    api_finding = AgentFinding(
        agent="api",
        label="API Compatibility",
        applicable=True,
        files_reviewed=["backend/app/main.py"],
        findings=["API return type changed for fetchHistory"],
        structured_findings=[
            finding_validation.normalize_finding(
                {
                    "title": "API return type changed for fetchHistory",
                    "evidence": "Return annotation changed.",
                    "severity": "P2",
                    "confidence": "MEDIUM",
                }
            )
        ],
        confidence=70,
    )
    state = {"pr": pr, "heuristics": heuristics, "api_finding": api_finding}
    prompt = _build_coordinator_prompt(state)
    assert "P2/MEDIUM" in prompt
    assert "API return type changed for fetchHistory" in prompt


# --- TEST 8: deterministic HIGH risk still results in BLOCK even when LLM says MEDIUM -

def test_deterministic_high_still_blocks_regardless_of_llm_medium():
    risk, decision = evaluate_policy(75)
    assert risk == RiskLevel.HIGH
    assert decision == ReleaseDecision.BLOCK

    disagreement = audit_llm_disagreement(RiskLevel.HIGH, RiskLevel.MEDIUM, ai_enabled=True)
    assert disagreement.detected
    assert disagreement.final_risk == RiskLevel.HIGH
    assert decide_release(disagreement.final_risk) == ReleaseDecision.BLOCK


# --- TEST 9: the report explains the deterministic override --------------------------

def test_report_renders_deterministic_override_explanation():
    from engine.models import AnalyzeResponse, LLMDisagreement, RiskReport, RepositoryMetadata
    from engine.models import HeuristicResult, PullRequestData, RepositoryInfo, ChangedFile
    from engine.models import AIAnalysis
    from engine.report_renderer import render_markdown

    pr = PullRequestData(
        owner="acme", repo="widgets", number=4, title="risky change", author="octocat",
        url="https://github.com/acme/widgets/pull/4", state="open", additions=50, deletions=5,
        changed_files_count=1,
        files=[ChangedFile(filename="config/settings.yml", status="modified", additions=50, deletions=5, changes=55)],
        repository=RepositoryInfo(owner="acme", name="widgets", full_name="acme/widgets"),
    )
    heuristics = HeuristicResult(score=75, factors=[], tests_touched=False, tests_deleted=False, migration_touched=False)
    disagreement = LLMDisagreement(
        detected=True,
        deterministic_risk=RiskLevel.HIGH,
        llm_risk=RiskLevel.MEDIUM,
        final_risk=RiskLevel.HIGH,
        direction="optimistic",
        reason="LLM assessed MEDIUM release risk while deterministic policy classified HIGH.",
    )
    report = RiskReport(
        decision="BLOCK",
        release_risk=RiskLevel.HIGH,
        llm_disagreement=disagreement,
        risk_score=75,
        confidence=60,
        deployment_strategy="Manual Approval",
        repository_metadata=RepositoryMetadata(files_changed_count=1),
    )
    response = AnalyzeResponse(
        pr=pr,
        heuristics=heuristics,
        ai=AIAnalysis(
            overall_risk=RiskLevel.MEDIUM, confidence=60, summary="s", architectural_impact="a",
            rollout_strategy="Manual Approval", rollout_reason="r", rollback_required=False,
        ),
        report=report,
        ai_enabled=True,
    )
    markdown = render_markdown(response)
    assert "Deterministic Override" in markdown
    assert "`HIGH`" in markdown
    assert "`MEDIUM`" in markdown


# --- TEST 10: existing report rendering tests still pass — see test_report_renderer.py
