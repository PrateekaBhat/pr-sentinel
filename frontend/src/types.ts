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
}

export interface AnalyzeResponse {
  pr: PullRequestData;
  heuristics: HeuristicResult;
  ai: AIAnalysis;
  ai_enabled: boolean;
  ai_error?: string | null;
  source: "live" | "demo";
}

export interface DemoSummary {
  id: string;
  title: string;
  repo: string;
  pr_number: number;
  tagline: string;
}
