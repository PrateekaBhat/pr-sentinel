export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export type ReleaseDecision = "ALLOW" | "NEEDS_REVIEW" | "BLOCK";

export interface LLMDisagreement {
  detected: boolean;
  deterministic_risk: RiskLevel;
  llm_risk?: RiskLevel | null;
  final_risk: RiskLevel;
  direction?: string | null;
  reason: string;
}

export interface ReviewComplexityResult {
  score: number;
  level: RiskLevel;
  drivers: string[];
}

export interface ReviewQueueItem {
  priority: string;
  filename: string;
  role: string;
  why_it_matters: string;
  potential_regression: string;
  suggested_validation: string;
  estimated_minutes: number;
}

export interface SpecialistRoutingEntry {
  domain: string;
  label: string;
  status: string;
  trigger: string;
  files_count: number;
  duration_ms: number;
  llm_call_made: boolean;
  files: string[];
}

export interface GoldenTestEntry {
  id: string;
  name: string;
  passed: boolean;
  expected: string;
  actual: string;
}

export interface GoldenTestsResponse {
  title: string;
  passed: number;
  total: number;
  tests: GoldenTestEntry[];
}

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
  review_signals?: HeuristicFactor[];
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
  level?: string;
  repository_context_available: boolean;
  llm_heuristic_agreement: boolean;
  evidence_completeness: "complete" | "partial";
  narrative: string;
  checks: RiskFactorFlag[];
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
  risk_density: number;
  critical_file_ratio: number;
  test_ratio: number;
  dependency_churn: number;
  documentation_ratio: number;
  average_file_diff_size: number;
  hotspot_concentration_pct: number;
}

/** A single 0-100 "is this ready to ship" score, derived deterministically
 * from risk, confidence, tests, deployment complexity, docs, secrets, and
 * dependency churn. */
export interface ProductionReadinessScore {
  score: number;
  label: "Ready" | "Needs attention" | "Not ready" | string;
  deductions: string[];
}

/** One actionable pre-merge task, generated from a detected risk rather than
 * a static template. */
export interface ChecklistItem {
  task: string;
  reason: string;
}

/** A reassuring, evidence-backed fact -- the mirror image of a triggered risk
 * factor. Explains why the score ISN'T higher, not just that it isn't. */
export interface PositiveSignal {
  label: string;
  reason: string;
}

/** An area PR Sentinel could NOT assess, and why -- an explicit admission of
 * a gap rather than a silent omission or an overconfident guess. */
export interface UncertaintyItem {
  area: string;
  reason: string;
}

/** A reviewer role/team recommendation derived from which subsystems this PR
 * touches -- a deterministic stand-in for a CODEOWNERS lookup. Not a specific
 * person: recommends the role that owns the affected area, backed by the
 * matched file paths. */
export interface SuggestedReviewer {
  role: string;
  reason: string;
  matched_paths: string[];
  required: boolean;
}

/** A row from the /api/history endpoint: one persisted completed analysis. */
export interface HistoryEntry {
  id: number;
  repository: string;
  pr_number: number;
  pr_title: string;
  author: string;
  analyzed_at: string;
  decision: string;
  overall_risk: string;
  risk_score: number;
  confidence: number;
  deployment_recommendation: string;
  total_duration_ms: number;
  files_changed: number;
  additions: number;
  deletions: number;
  heuristic_score: number;
  categories_triggered: string[];
  agent_decisions: Array<{
    agent: string;
    label: string;
    decision: string;
    confidence: number;
    execution_time_ms: number;
  }>;
  human_decision: string | null;
  human_reason: string | null;
}

/** Aggregate stats from /api/repository-health, powering the dashboard's
 * Repository Health panel. */
export interface RepositoryHealth {
  repository: string | null;
  analyses_count: number;
  average_risk_score: number;
  average_confidence: number;
  average_files_changed: number;
  average_review_duration_ms: number;
  deployment_distribution: Record<string, number>;
  top_recurring_categories: Array<[string, number]>;
  risk_trend: Array<{ analyzed_at: string; pr_number: number; risk_score: number }>;
  decision_trend: Array<{ analyzed_at: string; pr_number: number; decision: string }>;
}

export interface RiskReport {
  decision: string;
  release_risk?: RiskLevel;
  review_complexity?: ReviewComplexityResult | null;
  llm_disagreement?: LLMDisagreement | null;
  specialist_routing?: SpecialistRoutingEntry[];
  review_queue?: ReviewQueueItem[];
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
  production_readiness?: ProductionReadinessScore | null;
  suggested_reviewers: SuggestedReviewer[];
  positive_signals: PositiveSignal[];
  uncertainties: UncertaintyItem[];
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
  policy_note?: string;
}

export interface DemoSummary {
  id: string;
  title: string;
  repo: string;
  pr_number: number;
  tagline: string;
}
