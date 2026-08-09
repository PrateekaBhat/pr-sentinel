import { useEffect, useState } from "react";

import { analyzePullRequest, ApiError, fetchDemo, fetchDemos, fetchRepositoryHealth } from "./api/client";
import AgentPipelinePanel from "./components/AgentPipelinePanel";
import ArchitecturalImpactCard from "./components/ArchitecturalImpactCard";
import Card from "./components/Card";
import CategoryBreakdown from "./components/CategoryBreakdown";
import CitationsList from "./components/CitationsList";
import ConfidenceCard from "./components/ConfidenceCard";
import DemoGallery from "./components/DemoGallery";
import EmptyState from "./components/EmptyState";
import EngineeringMetricsCard from "./components/EngineeringMetricsCard";
import FileRiskList from "./components/FileRiskList";
import Header from "./components/Header";
import JudgeBadge from "./components/JudgeBadge";
import LoadingState from "./components/LoadingState";
import OperationalChecklistCard from "./components/OperationalChecklistCard";
import SuggestedReviewersCard from "./components/SuggestedReviewersCard";
import PositiveSignalsCard from "./components/PositiveSignalsCard";
import UncertaintyCard from "./components/UncertaintyCard";
import ProductionReadinessGauge from "./components/ProductionReadinessGauge";
import RepoInput from "./components/RepoInput";
import RepositoryHealthPanel from "./components/RepositoryHealthPanel";
import RiskGauge from "./components/RiskGauge";
import RolloutCard from "./components/RolloutCard";
import TestAreasCard from "./components/TestAreasCard";
import type { AnalyzeResponse, DemoSummary, RepositoryHealth } from "./types";

export default function App() {
  const [demos, setDemos] = useState<DemoSummary[]>([]);
  const [activeDemoId, setActiveDemoId] = useState<string | undefined>();
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [repoHealth, setRepoHealth] = useState<RepositoryHealth | null>(null);

  useEffect(() => {
    fetchDemos().then(setDemos).catch(() => setDemos([]));
  }, []);

  useEffect(() => {
    if (!result) {
      setRepoHealth(null);
      return;
    }
    fetchRepositoryHealth({ repository: `${result.pr.owner}/${result.pr.repo}` })
      .then(setRepoHealth)
      .catch(() => setRepoHealth(null));
  }, [result]);

  async function handleAnalyze(prUrl: string) {
    setLoading(true);
    setError(null);
    setActiveDemoId(undefined);
    try {
      const res = await analyzePullRequest(prUrl);
      setResult(res);
    } catch (err) {
      setResult(null);
      setError(err instanceof ApiError ? err.message : "Something went wrong. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectDemo(id: string) {
    setLoading(true);
    setError(null);
    setActiveDemoId(id);
    try {
      const res = await fetchDemo(id);
      setResult(res);
    } catch {
      setError("Couldn't load that demo. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen font-body">
      <Header />

      <main className="mx-auto max-w-6xl px-6 py-10">
        <div className="mb-8 flex flex-col gap-4">
          <RepoInput onAnalyze={handleAnalyze} loading={loading} />
          <DemoGallery demos={demos} onSelect={handleSelectDemo} activeId={activeDemoId} />
          {error && (
            <p className="rounded-md border border-risk-high/40 bg-risk-high/10 px-4 py-2 text-sm text-risk-high">
              {error}
            </p>
          )}
        </div>

        {loading && <LoadingState />}

        {!loading && !result && !error && <EmptyState />}

        {!loading && result && (
          <div className="flex flex-col gap-6">
            <div className="flex items-center justify-between rounded-lg border border-steel bg-panel px-5 py-3 shadow-panel">
              <div>
                <p className="font-mono text-xs text-fog">
                  {result.pr.owner}/{result.pr.repo} · #{result.pr.number}
                </p>
                <h2 className="font-display text-base font-semibold text-paper">
                  {result.pr.title}
                </h2>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`rounded-full px-2.5 py-1 font-mono text-[11px] font-semibold ${
                    result.report.decision === "BLOCK"
                      ? "bg-risk-high/15 text-risk-high"
                      : "bg-risk-low/15 text-risk-low"
                  }`}
                >
                  {result.report.decision}
                </span>
                <JudgeBadge judge={result.judge} />
                {!result.ai_enabled && (
                  <span
                    className="max-w-xs shrink-0 truncate rounded-md border border-amber/40 bg-amber/10 px-2.5 py-1 font-mono text-[11px] text-amber"
                    title={result.ai_error ?? undefined}
                  >
                    Heuristics only — {result.ai_error ?? "Ollama unavailable"}
                  </span>
                )}
              </div>
            </div>

            <Card title="Executive summary" eyebrow="Coordinator agent synthesis">
              <p className="text-sm leading-relaxed text-paper">
                {result.report.executive_summary || result.ai.summary}
              </p>
            </Card>

            {repoHealth && repoHealth.analyses_count > 0 && (
              <Card title="Repository health" eyebrow={`${result.pr.owner}/${result.pr.repo}`}>
                <RepositoryHealthPanel health={repoHealth} />
              </Card>
            )}

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              <Card title="Overall risk" eyebrow="Sentinel assessment" className="flex flex-col items-center justify-center lg:col-span-1">
                <RiskGauge risk={result.ai.overall_risk} evidenceConfidence={result.report.confidence_explanation?.level ?? "MEDIUM"} />
                <p className="mt-3 text-center text-sm text-fog">Risk score: {result.report.risk_score}/100</p>
              </Card>

              <Card title="Risk score breakdown" eyebrow="By category" className="lg:col-span-2">
                <CategoryBreakdown categories={result.report.risk_categories} />
              </Card>
            </div>

            {result.report.production_readiness && (
              <Card title="Production readiness" eyebrow="Derived score">
                <ProductionReadinessGauge readiness={result.report.production_readiness} />
              </Card>
            )}

            <Card title="Architectural impact" eyebrow="Affected subsystems">
              <ArchitecturalImpactCard impact={result.report.architectural_impact} />
              {result.ai.operational_risks.length > 0 && (
                <ul className="mt-3 flex flex-col gap-1.5 border-t border-steel pt-3">
                  {result.ai.operational_risks.map((risk) => (
                    <li key={risk} className="flex items-start gap-2 text-sm text-fog">
                      <span className="mt-0.5 text-amber">▲</span>
                      {risk}
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            {result.report.engineering_metrics && (
              <Card title="Engineering change summary" eyebrow="Deterministic metrics">
                <EngineeringMetricsCard metrics={result.report.engineering_metrics} />
              </Card>
            )}

            <Card title="Agent pipeline" eyebrow="LangGraph execution">
              <AgentPipelinePanel decisions={result.report.agent_decisions} />
            </Card>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <Card title="Files most likely to cause production issues" eyebrow="Hotspots">
                <FileRiskList files={result.ai.file_risks} />
              </Card>

              <div className="flex flex-col gap-6">
                <Card title="Deployment recommendation" eyebrow="Rollout strategy">
                  {result.report.deployment_recommendation ? (
                    <RolloutCard
                      strategy={result.report.deployment_recommendation.strategy}
                      reason={result.report.deployment_recommendation.reason}
                      rollbackRequired={result.report.deployment_recommendation.rollback_required}
                      alternativesConsidered={result.report.deployment_recommendation.alternatives_considered}
                    />
                  ) : (
                    <RolloutCard
                      strategy={result.ai.rollout_strategy}
                      reason={result.ai.rollout_reason}
                      rollbackRequired={result.ai.rollback_required}
                    />
                  )}
                </Card>
                <Card title="Suggested test areas" eyebrow="Before you merge">
                  <TestAreasCard
                    areas={result.ai.suggested_test_areas}
                    coveragePct={result.ai.test_coverage_estimate_pct}
                  />
                </Card>
                {result.report.operational_checklist.length > 0 && (
                  <Card title="Operational checklist" eyebrow="Before merge">
                    <OperationalChecklistCard items={result.report.operational_checklist} />
                  </Card>
                )}
                {result.report.suggested_reviewers.length > 0 && (
                  <Card title="Suggested reviewers" eyebrow="Who should sign off">
                    <SuggestedReviewersCard reviewers={result.report.suggested_reviewers} />
                  </Card>
                )}
                {result.report.positive_signals.length > 0 && (
                  <Card title="Why this isn't rated higher" eyebrow="Positive evidence">
                    <PositiveSignalsCard signals={result.report.positive_signals} />
                  </Card>
                )}
                {result.report.uncertainties.length > 0 && (
                  <Card title="What we couldn't determine" eyebrow="Known gaps in this analysis">
                    <UncertaintyCard items={result.report.uncertainties} />
                  </Card>
                )}
              </div>
            </div>

            <Card title="Repository context (RAG)" eyebrow="Retrieved documents & snippets">
              <CitationsList rag={result.rag} />
            </Card>

            <Card title="Confidence" eyebrow="Evidence-backed explanation">
              {result.report.confidence_explanation ? (
                <ConfidenceCard confidence={result.report.confidence_explanation} />
              ) : (
                <p className="text-sm text-fog">{result.report.confidence}% confidence.</p>
              )}
            </Card>
          </div>
        )}
      </main>
    </div>
  );
}
