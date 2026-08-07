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
    score: int  # 0-100
    factors: list[HeuristicFactor]
    score_math: list[ScoreMathFactor] = Field(default_factory=list)
    tests_touched: bool
    tests_deleted: bool
    migration_touched: bool


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
    """Explains *why* the model is as confident as it is, instead of a bare number."""

    score: int  # 0-100
    level: str = "Medium"  # "High" | "Medium" | "Low" — human-readable tier derived from score
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


class ExecutionMetrics(BaseModel):
    generated_at: str
    total_duration_ms: int
    ai_enabled: bool
    rag_cache_hit: bool = False


class RiskReport(BaseModel):
    decision: str
    risk_score: int
    confidence: int
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


class DemoSummary(BaseModel):
    id: str
    title: str
    repo: str
    pr_number: int
    tagline: str
