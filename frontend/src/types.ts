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
  cache_hit: boolean;
  indexed_doc_paths: string[];
}

export type AgentDomain = "security" | "performance" | "database" | "api" | "tests";

export interface AgentFinding {
  agent: AgentDomain;
  label: string;
  applicable: boolean;
  files_reviewed: string[];
  findings: string[];
  risk_note: string;
  confidence: number;
}

/** Surfaces one node's execution inside the LangGraph pipeline. */
export interface AgentDecision {
  agent: string;
  label: string;
  decision: string;
  reasoning: string;
  confidence: number;
  execution_time_ms: number;
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

/** One structured piece of evidence: exactly what changed, why it matters, how
 * confident we are, how severe it is, and what to do about it. */
export interface EvidenceItem {
  file_path: string;
  snippet?: string | null;
  explanation: string;
  confidence: number;
  severity: RiskLevel;
  recommended_action: string;
}

/** One row of the fixed risk-category taxonomy (Authentication, API, Database, ...). */
export interface RiskCategory {
  category: string;
  score: number;
  status: RiskLevel;
  summary: string;
  evidence: EvidenceItem[];
  reasons: string[];
  evidence_files: string[];
}

export interface ArchitecturalImpact {
  affected_subsystems: string[];
  narrative: string;
}

export interface ConfidenceExplanation {
  score: number;
  repository_context_available: boolean;
  llm_heuristic_agreement: boolean;
  evidence_completeness: "complete" | "partial";
  narrative: string;
}

export interface DeploymentRecommendation {
  strategy: "Standard" | "Canary" | "Blue/Green" | "Manual Approval" | string;
  reason: string;
  alternatives_considered: string[];
  rollback_required: boolean;
}

export interface ExecutionMetrics {
  generated_at: string;
  total_duration_ms: number;
  ai_enabled: boolean;
  rag_cache_hit: boolean;
}

/** Deterministic counts describing the shape of the change — an expansion of
 * "files changed" into what an engineer wants to know before reviewing. */
export interface EngineeringMetrics {
  public_apis_modified: number;
  api_routes_changed: number;
  config_files_changed: number;
  workflow_files_changed: number;
  documentation_files_changed: number;
  documentation_coverage_pct: number;
  test_files_touched: number;
  test_coverage_delta_files: number;
  dependency_updates: number;
  lines_added: number;
  lines_removed: number;
  deleted_files: number;
  largest_file: string;
  largest_file_changes: number;
  most_impacted_subsystem: string;
}

/** One actionable pre-merge task, generated from a detected risk rather than
 * a static template. */
export interface ChecklistItem {
  task: string;
  reason: string;
}

export interface RiskReport {
  decision: string;
  risk_score: number;
  confidence: number;
  deployment_strategy: string;
  risk_breakdown: Record<string, number>;
  risk_categories: RiskCategory[];
  findings: string[];
  evidence: string[];
  timeline: TimelineStage[];
  agent_statuses: AgentStatus[];
  agent_decisions: AgentDecision[];
  repository_metadata: RepositoryMetadata;
  execution_metrics?: ExecutionMetrics | null;
  summary: string;
  executive_summary: string;
  high_risk_files: string[];
  architectural_impact: ArchitecturalImpact;
  confidence_explanation?: ConfidenceExplanation | null;
  deployment_recommendation?: DeploymentRecommendation | null;
  engineering_metrics?: EngineeringMetrics | null;
  operational_checklist: ChecklistItem[];
}

export interface AIAnalysis {
  overall_risk: RiskLevel;
  confidence: number;
  summary: string;
  executive_summary: string;
  architectural_impact: string;
  affected_subsystems: string[];
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
