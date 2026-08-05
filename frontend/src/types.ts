export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export interface ChangedFile {
  filename: string;
  status: string;
  additions: number;
  deletions: number;
  changes: number;
  patch?: string | null;
}

export interface PullRequestData {
  owner: string;
  repo: string;
  number: number;
  title: string;
  body?: string;
  author: string;
  url: string;
  additions: number;
  deletions: number;
  changed_files_count: number;
  labels: string[];
  commit_messages: string[];
  files: ChangedFile[];
}

export interface HeuristicFactor {
  key: string;
  label: string;
  triggered: boolean;
  weight: number;
  reason: string;
}

export interface HeuristicResult {
  score: number;
  factors: HeuristicFactor[];
  tests_touched: boolean;
  tests_deleted: boolean;
  migration_touched: boolean;
}

export interface FileRisk {
  filename: string;
  risk: RiskLevel;
  reason: string;
}

export interface RiskFactorFlag {
  key: string;
  label: string;
  passed: boolean;
}

export interface RAGChunk {
  path: string;
  snippet: string;
  score: number;
}

export interface RAGContext {
  scanned: boolean;
  default_branch?: string | null;
  indexed_files: number;
  chunks_indexed: number;
  skip_reason?: string | null;
  retrieved: RAGChunk[];
}

export type AgentDomain = "security" | "performance" | "database" | "api" | "tests";

export interface AgentFinding {
  agent: AgentDomain;
  label: string;
  applicable: boolean;
  files_reviewed: string[];
  findings: string[];
  risk_note: string;
}

export interface JudgeVerdict {
  grounded: boolean;
  issues: string[];
  notes: string;
}

export interface TimelineStage {
  stage: string;
  duration_ms: number;
}

export interface AgentStatus {
  agent: string;
  label: string;
  status: string;
  files_reviewed: number;
  duration_ms: number;
}

export interface RepositoryMetadata {
  default_branch?: string | null;
  technologies: string[];
  files_changed_count: number;
}

export interface RiskReport {
  decision: string;
  risk_score: number;
  confidence: number;
  deployment_strategy: string;
  risk_breakdown: Record<string, number>;
  findings: string[];
  evidence: string[];
  timeline: TimelineStage[];
  agent_statuses: AgentStatus[];
  repository_metadata: RepositoryMetadata;
}

export interface AIAnalysis {
  overall_risk: RiskLevel;
  confidence: number;
  summary: string;
  architectural_impact: string;
  operational_risks: string[];
  rollout_strategy: string;
  rollout_reason: string;
  rollback_required: boolean;
  test_coverage_estimate_pct?: number | null;
  suggested_test_areas: string[];
  risk_factors: RiskFactorFlag[];
  file_risks: FileRisk[];
  agent_findings: AgentFinding[];
  citations: RAGChunk[];
}

export interface AnalyzeResponse {
  pr: PullRequestData;
  heuristics: HeuristicResult;
  ai: AIAnalysis;
  report: RiskReport;
  ai_enabled: boolean;
  ai_error?: string | null;
  rag: RAGContext;
  judge?: JudgeVerdict | null;
  source: "live" | "demo";
}

export interface DemoSummary {
  id: string;
  title: string;
  repo: string;
  pr_number: number;
  tagline: string;
}
