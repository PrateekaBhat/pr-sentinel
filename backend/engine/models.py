from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    pr_url: str = Field(..., description="Full GitHub pull request URL")


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ReleaseDecision(str, Enum):
    ALLOW = "ALLOW"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCK = "BLOCK"


class LLMDisagreement(BaseModel):
    """Audit record when LLM release-risk assessment diverges from deterministic policy."""

    detected: bool
    deterministic_risk: RiskLevel
    llm_risk: RiskLevel | None = None
    final_risk: RiskLevel
    direction: str | None = None  # "optimistic" | "pessimistic"
    reason: str


class ReviewComplexityResult(BaseModel):
    """How hard this PR is to review — separate from release risk."""

    score: int  # 0-100
    level: RiskLevel
    drivers: list[str] = Field(default_factory=list)


class ReviewQueueItem(BaseModel):
    priority: str  # P1 | P2 | P3 | P4
    filename: str
    role: str
    why_it_matters: str
    potential_regression: str
    suggested_validation: str
    estimated_minutes: int


class SpecialistRoutingEntry(BaseModel):
    """Explainable specialist agent routing diagnostic."""

    domain: str
    label: str
    status: str  # EXECUTED | SKIPPED
    trigger: str
    files_count: int
    duration_ms: int = 0
    llm_call_made: bool = False
    files: list[str] = Field(default_factory=list)


class ChangedFile(BaseModel):
    filename: str
    status: str  # added | modified | removed | renamed
    additions: int
    deletions: int
    changes: int
    patch: Optional[str] = None


class RepositoryInfo(BaseModel):
    owner: str
    name: str
    full_name: str
    description: Optional[str] = None
    primary_language: Optional[str] = None
    stars: int = 0
    topics: list[str] = Field(default_factory=list)
    default_branch: Optional[str] = None
    framework: Optional[str] = None
    size_kb: int = 0


class PullRequestData(BaseModel):
    owner: str
    repo: str
    number: int
    title: str
    body: Optional[str] = ""
    author: str
    url: str
    created_at: Optional[str] = None
    mergeable_state: Optional[str] = None
    mergeable: Optional[bool] = None
    state: str
    additions: int
    deletions: int
    changed_files_count: int
    labels: list[str] = Field(default_factory=list)
    commit_messages: list[str] = Field(default_factory=list)
    files: list[ChangedFile] = Field(default_factory=list)
    repository: RepositoryInfo
    head_branch: Optional[str] = None
    base_branch: Optional[str] = None


class HeuristicFactor(BaseModel):
    key: str
    label: str
    triggered: bool
    weight: int
    reason: str


class ScoreMathFactor(BaseModel):
    factor: str
    points: int
    reason: str


class HeuristicResult(BaseModel):
    score: int  # 0-100 release-risk score (excludes diff-size signals)
    factors: list[HeuristicFactor]
    score_math: list[ScoreMathFactor] = Field(default_factory=list)
    tests_touched: bool
    tests_deleted: bool
    migration_touched: bool
    review_signals: list[HeuristicFactor] = Field(default_factory=list)  # diff-size etc., not in release score


class FileRisk(BaseModel):
    filename: str
    risk: RiskLevel
    reason: str


class RiskFactorFlag(BaseModel):
    key: str
    label: str
    passed: bool  # True = green check, False = flagged concern


class RAGChunk(BaseModel):
    """A retrieved slice of repository documentation, used as a citation."""

    path: str
    snippet: str
    score: float = 0.0  # cosine similarity score; positive = more relevant
    retrieval_reason: str = ""  # human-readable explanation of why this chunk was retrieved


class RAGContext(BaseModel):
    scanned: bool  # whether repository docs were successfully indexed
    default_branch: Optional[str] = None
    indexed_files: int = 0
    chunks_indexed: int = 0
    skip_reason: Optional[str] = None
    retrieved: list[RAGChunk] = Field(default_factory=list)
    cache_hit: bool = False
    indexed_doc_paths: list[str] = Field(default_factory=list)


class AgentFinding(BaseModel):
    """One specialist agent's output. Agents that found no relevant files skip the
    LLM call entirely and report applicable=False — this is what makes routing real
    instead of decorative."""

    agent: str  # "security" | "performance" | "database" | "api" | "tests"
    label: str
    applicable: bool
    files_reviewed: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    risk_note: str = ""
    confidence: int = 60  # 0-100, how confident this agent is in its own findings


class AgentDecision(BaseModel):
    """Surfaces one node's execution inside the LangGraph pipeline: what it decided,
    why, how confident it was, and how long it took. This is what makes the multi-agent
    graph auditable rather than a black box."""

    agent: str
    label: str
    decision: str  # e.g. "Skipped — no files in domain" | "No concerns raised" | "Concerns raised"
    reasoning: str
    confidence: int  # 0-100
    execution_time_ms: int


class JudgeVerdict(BaseModel):
    """Lightweight LLM-as-judge pass over the coordinator's output, checking that its
    claims trace back to evidence the agents/heuristics actually produced."""

    grounded: bool
    issues: list[str] = Field(default_factory=list)
    notes: str = ""


class TimelineStage(BaseModel):
    stage: str
    duration_ms: int


class AgentStatus(BaseModel):
    agent: str
    label: str
    status: str
    files_reviewed: int
    duration_ms: int


class RepositoryMetadata(BaseModel):
    default_branch: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)
    files_changed_count: int


class EvidenceItem(BaseModel):
    """A single, structured piece of evidence backing a finding: exactly what file,
    what changed, why it matters, how confident we are, how severe it is, and what to
    do about it. This is the atomic unit auditors trace claims back to."""

    file_path: str
    snippet: Optional[str] = None  # code / diff excerpt or retrieved RAG context
    explanation: str
    confidence: int  # 0-100
    severity: RiskLevel
    recommended_action: str


class RiskCategory(BaseModel):
    """One row of the risk score breakdown, e.g. 'Authentication' or 'CI/CD'."""

    category: str
    score: int  # 0-100
    status: RiskLevel
    summary: str = ""
    evidence: list[EvidenceItem] = Field(default_factory=list)
    # legacy fields kept for renderer / frontend backward compatibility
    reasons: list[str] = Field(default_factory=list)
    evidence_files: list[str] = Field(default_factory=list)


class ArchitecturalImpact(BaseModel):
    """Which subsystems this PR touches and how they relate, in plain English."""

    affected_subsystems: list[str] = Field(default_factory=list)
    narrative: str = ""


class ConfidenceExplanation(BaseModel):
    """Evidence confidence tier — qualitative, not a calibrated probability."""

    score: int  # 0-100 internal score; UI emphasizes level tier
    level: str = "MEDIUM"  # HIGH | MEDIUM | LOW — Evidence Confidence tier
    repository_context_available: bool
    llm_heuristic_agreement: bool
    evidence_completeness: str  # "complete" | "partial"
    narrative: str = ""
    checks: list[RiskFactorFlag] = Field(default_factory=list)  # ✓/✗ explainability checklist


class DeploymentRecommendation(BaseModel):
    """The chosen rollout strategy plus reasoning, monitoring, rollback, and approval rules."""

    strategy: str  # "Standard" | "Canary" | "Blue/Green" | "Manual Approval"
    reason: str = ""
    monitoring_focus: str = ""
    rollback_trigger: str = ""
    approval_level: str = ""
    alternatives_considered: list[str] = Field(default_factory=list)
    rollback_required: bool = False


class RepositoryIntelligence(BaseModel):
    primary_language: Optional[str] = None
    framework: Optional[str] = None
    containerization: Optional[str] = None
    ci_provider: Optional[str] = None
    infrastructure: list[str] = Field(default_factory=list)
    estimated_size: str = "unknown"
    default_branch: Optional[str] = None


class EngineeringMetrics(BaseModel):
    """Deterministic counts describing the shape of the change — an expansion of
    'files changed' into what an engineer wants to know before reviewing."""

    public_apis_modified: int = 0
    api_routes_changed: int = 0
    config_files_changed: int = 0
    workflow_files_changed: int = 0
    documentation_files_changed: int = 0
    documentation_coverage_pct: int = 0
    test_files_touched: int = 0
    test_coverage_delta_files: int = 0
    dependency_updates: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    deleted_files: int = 0
    largest_file: str = "n/a"
    largest_file_changes: int = 0
    most_impacted_subsystem: str = "None"
    # Ratio metrics
    risk_density: float = 0.0            # risk score / files changed
    critical_file_ratio: float = 0.0     # critical files / total files
    test_ratio: float = 0.0              # test files touched / code files touched
    dependency_churn: int = 0            # alias of dependency_updates, kept explicit per spec
    documentation_ratio: float = 0.0     # doc files / total files
    average_file_diff_size: float = 0.0  # (additions+deletions) / files changed
    hotspot_concentration_pct: int = 0   # largest file's share of total diff churn


class ProductionReadinessScore(BaseModel):
    """A single 0-100 'is this ready to ship' score, derived deterministically
    from risk, confidence, tests, deployment complexity, docs, secrets, and
    dependency churn — every point deducted is explained in `deductions`."""

    score: int
    label: str  # "Ready" | "Needs attention" | "Not ready"
    deductions: list[str] = Field(default_factory=list)


class ChecklistItem(BaseModel):
    """One actionable pre-merge task, generated from a detected risk rather
    than a static template."""

    task: str
    reason: str


class PositiveSignal(BaseModel):
    """A reassuring, evidence-backed fact -- the mirror image of a triggered risk
    factor. Every risk report explains what's dangerous; this explains what
    ISN'T, so a LOW-risk verdict is backed by explicit absence-of-risk evidence
    rather than just a lack of alarms."""

    label: str
    reason: str


class UncertaintyItem(BaseModel):
    """An area PR Sentinel could NOT assess, and why -- explicit admission of a
    gap rather than silently omitting it or guessing. Distinct from a
    PositiveSignal: this isn't 'no risk found', it's 'insufficient evidence to
    make a determination either way'."""

    area: str
    reason: str


class SuggestedReviewer(BaseModel):
    """A reviewer role/team recommendation derived from which subsystems this PR
    touches -- a lightweight, deterministic stand-in for a CODEOWNERS lookup.
    Not a specific person: PR Sentinel doesn't have access to org membership,
    so it recommends the *role* that owns the affected area and the evidence
    (matched files) behind that recommendation."""

    role: str
    reason: str
    matched_paths: list[str] = Field(default_factory=list)
    required: bool = False  # True = should block merge without this reviewer's sign-off


class ExecutionMetrics(BaseModel):
    generated_at: str
    total_duration_ms: int
    ai_enabled: bool
    rag_cache_hit: bool = False


class RiskReport(BaseModel):
    decision: str  # ALLOW | NEEDS_REVIEW | BLOCK — from deterministic policy
    release_risk: RiskLevel = RiskLevel.LOW
    review_complexity: ReviewComplexityResult | None = None
    llm_disagreement: LLMDisagreement | None = None
    specialist_routing: list[SpecialistRoutingEntry] = Field(default_factory=list)
    review_queue: list[ReviewQueueItem] = Field(default_factory=list)
    risk_score: int  # deterministic release-risk score
    confidence: int  # internal; prefer confidence_explanation.level in UI
    review_effort_minutes: int = 15
    review_effort_label: str = "15 minutes"
    deployment_strategy: str
    score_math: list[ScoreMathFactor] = Field(default_factory=list)
    risk_breakdown: dict[str, int] = Field(default_factory=dict)
    risk_categories: list[RiskCategory] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    timeline: list[TimelineStage] = Field(default_factory=list)
    agent_statuses: list[AgentStatus] = Field(default_factory=list)
    agent_decisions: list[AgentDecision] = Field(default_factory=list)
    repository_metadata: RepositoryMetadata
    repository_intelligence: RepositoryIntelligence = Field(default_factory=RepositoryIntelligence)
    execution_metrics: Optional[ExecutionMetrics] = None
    summary: str = ""
    executive_summary: str = ""
    high_risk_files: list[str] = Field(default_factory=list)
    architectural_impact: ArchitecturalImpact = Field(default_factory=ArchitecturalImpact)
    confidence_explanation: Optional[ConfidenceExplanation] = None
    deployment_recommendation: Optional[DeploymentRecommendation] = None
    engineering_metrics: Optional[EngineeringMetrics] = None
    operational_checklist: list[ChecklistItem] = Field(default_factory=list)
    production_readiness: Optional[ProductionReadinessScore] = None
    suggested_reviewers: list[SuggestedReviewer] = Field(default_factory=list)
    positive_signals: list[PositiveSignal] = Field(default_factory=list)
    uncertainties: list[UncertaintyItem] = Field(default_factory=list)


class AIAnalysis(BaseModel):
    overall_risk: RiskLevel
    confidence: int  # 0-100
    summary: str
    executive_summary: str = ""
    architectural_impact: str
    affected_subsystems: list[str] = Field(default_factory=list)
    operational_risks: list[str] = Field(default_factory=list)
    rollout_strategy: str
    rollout_reason: str
    rollback_required: bool
    test_coverage_estimate_pct: Optional[int] = None
    suggested_test_areas: list[str] = Field(default_factory=list)
    risk_factors: list[RiskFactorFlag] = Field(default_factory=list)
    file_risks: list[FileRisk] = Field(default_factory=list)
    agent_findings: list[AgentFinding] = Field(default_factory=list)
    citations: list[RAGChunk] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    pr: PullRequestData
    heuristics: HeuristicResult
    ai: AIAnalysis
    report: RiskReport
    ai_enabled: bool  # True if this response came from Ollama; False if heuristics-only fallback
    ai_error: Optional[str] = None  # set when ai_enabled is False and it was due to an error
    rag: RAGContext = Field(default_factory=lambda: RAGContext(scanned=False))
    judge: Optional[JudgeVerdict] = None
    source: str = "live"  # "live" or "demo"
    policy_note: str = ""  # e.g. AI synthesis unavailable message


class DemoSummary(BaseModel):
    id: str
    title: str
    repo: str
    pr_number: int
    tagline: str
