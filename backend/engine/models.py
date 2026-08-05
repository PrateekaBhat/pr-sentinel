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


class HeuristicResult(BaseModel):
    score: int  # 0-100
    factors: list[HeuristicFactor]
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
    score: float = 0.0  # similarity score, higher = more relevant


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


class RiskCategory(BaseModel):
    category: str
    score: int
    status: RiskLevel
    reasons: list[str] = Field(default_factory=list)
    evidence_files: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    category: str
    files: list[str] = Field(default_factory=list)
    reason: str


class RepositoryIntelligence(BaseModel):
    primary_language: Optional[str] = None
    framework: Optional[str] = None
    containerization: Optional[str] = None
    ci_provider: Optional[str] = None
    infrastructure: list[str] = Field(default_factory=list)
    estimated_size: str = "unknown"
    default_branch: Optional[str] = None


class ExecutionMetrics(BaseModel):
    generated_at: str
    total_duration_ms: int
    ai_enabled: bool
    rag_cache_hit: bool = False


class RiskReport(BaseModel):
    decision: str
    risk_score: int
    confidence: int
    deployment_strategy: str
    risk_breakdown: dict[str, int] = Field(default_factory=dict)
    risk_categories: list[RiskCategory] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    timeline: list[TimelineStage] = Field(default_factory=list)
    agent_statuses: list[AgentStatus] = Field(default_factory=list)
    repository_metadata: RepositoryMetadata
    repository_intelligence: RepositoryIntelligence = Field(default_factory=RepositoryIntelligence)
    execution_metrics: Optional[ExecutionMetrics] = None
    summary: str = ""
    high_risk_files: list[str] = Field(default_factory=list)


class AIAnalysis(BaseModel):
    overall_risk: RiskLevel
    confidence: int  # 0-100
    summary: str
    architectural_impact: str
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
