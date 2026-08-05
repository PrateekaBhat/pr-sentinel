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


class PullRequestData(BaseModel):
    owner: str
    repo: str
    number: int
    title: str
    body: Optional[str] = ""
    author: str
    url: str
    additions: int
    deletions: int
    changed_files_count: int
    labels: list[str] = Field(default_factory=list)
    commit_messages: list[str] = Field(default_factory=list)
    files: list[ChangedFile] = Field(default_factory=list)


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


class AnalyzeResponse(BaseModel):
    pr: PullRequestData
    heuristics: HeuristicResult
    ai: AIAnalysis
    ai_enabled: bool  # True if this response came from Ollama; False if heuristics-only fallback
    ai_error: Optional[str] = None  # set when ai_enabled is False and it was due to an error
    source: str = "live"  # "live" or "demo"


class DemoSummary(BaseModel):
    id: str
    title: str
    repo: str
    pr_number: int
    tagline: str
