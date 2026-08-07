import { useEffect, useMemo, useState } from "react";

import { analyzePullRequest, ApiError, fetchDemo, fetchDemos } from "./api/client";
import AgentPipelinePanel from "./components/AgentPipelinePanel";
import Card from "./components/Card";
import CategoryBreakdown from "./components/CategoryBreakdown";
import CitationsList from "./components/CitationsList";
import Collapsible from "./components/Collapsible";
import DemoGallery from "./components/DemoGallery";
import EmptyState from "./components/EmptyState";
import EngineeringMetricsCard from "./components/EngineeringMetricsCard";
import Header from "./components/Header";
import LoadingState from "./components/LoadingState";
import ProductionReadinessGauge from "./components/ProductionReadinessGauge";
import RepoInput from "./components/RepoInput";
import type { AnalyzeResponse, DemoSummary, EvidenceItem, FileRisk, RiskLevel } from "./types";

const severityRank: Record<RiskLevel, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };
const confidenceLevel = (score: number) => score >= 75 ? "High" : score >= 50 ? "Medium" : "Low";
const isPlaceholderPath = (path: string) => !path || path.startsWith("/path/to/");
const badgeFor = (result: AnalyzeResponse) => {
  const readiness = result.report.production_readiness?.score;
  if (result.report.decision === "BLOCK" || (readiness !== undefined && readiness < 55)) return "Do Not Merge";
  return result.report.decision === "ALLOW" && (readiness === undefined || readiness >= 80) ? "Ready" : "Review Needed";
};
const truncateWords = (text: string, max = 50) => {
  const words = text.split(/\s+/).filter(Boolean);
  return `${words.slice(0, max).join(" ")}${words.length > max ? "..." : ""}`;
};

export default function App() {
  const [demos, setDemos] = useState<DemoSummary[]>([]);
  const [activeDemoId, setActiveDemoId] = useState<string | undefined>();
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { fetchDemos().then(setDemos).catch(() => setDemos([])); }, []);
  const findings = useMemo(() => result ? result.report.risk_categories.flatMap((category) => category.evidence)
    .sort((a, b) => severityRank[a.severity] - severityRank[b.severity]).slice(0, 5) : [], [result]);
  const fileRisks = useMemo<FileRisk[]>(() => {
    if (!result) return [];
    const assessed = result.ai.file_risks.filter((file) => !isPlaceholderPath(file.filename));
    if (assessed.length) return assessed.sort((a, b) => severityRank[a.risk] - severityRank[b.risk]).slice(0, 3);
    return [...result.pr.files].sort((a, b) => b.changes - a.changes).slice(0, 3).map((file) => ({
      filename: file.filename, risk: result.ai.overall_risk, reason: `${file.changes} changed lines in this implementation file.`,
    }));
  }, [result]);

  async function run(action: () => Promise<AnalyzeResponse>) {
    setLoading(true); setError(null);
    try { setResult(await action()); }
    catch (err) { setResult(null); setError(err instanceof ApiError ? err.message : "Something went wrong. Is the backend running?"); }
    finally { setLoading(false); }
  }

  return <div className="min-h-screen font-body">
    <Header />
    <main className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-8 flex flex-col gap-4">
        <RepoInput onAnalyze={(url) => { setActiveDemoId(undefined); return run(() => analyzePullRequest(url)); }} loading={loading} />
        <DemoGallery demos={demos} onSelect={(id) => { setActiveDemoId(id); return run(() => fetchDemo(id)); }} activeId={activeDemoId} />
        {error && <p className="rounded-md border border-risk-high/40 bg-risk-high/10 px-4 py-2 text-sm text-risk-high">{error}</p>}
      </div>
      {loading && <LoadingState />}
      {!loading && !result && !error && <EmptyState />}
      {!loading && result && <Report result={result} findings={findings} fileRisks={fileRisks} />}
    </main>
  </div>;
}

function Report({ result, findings, fileRisks }: { result: AnalyzeResponse; findings: EvidenceItem[]; fileRisks: FileRisk[] }) {
  const { report, ai, pr } = result;
  const readiness = report.production_readiness;
  const confidence = report.confidence_explanation?.level || confidenceLevel(report.confidence);
  const deployment = report.deployment_recommendation?.strategy || report.deployment_strategy;
  const actionFor = (filename: string) => findings.find((item) => item.file_path === filename)?.recommended_action || "Review the changed lines and validate affected behavior.";
  const paths = pr.files.map((file) => file.filename.toLowerCase());
  const backendChanged = paths.some((path) => path.endsWith(".py") || path.includes("backend/"));
  const workflowChanged = paths.some((path) => path.includes(".github/workflows/") || path.includes("workflow"));
  const testsMissing = result.heuristics.factors.some((factor) => factor.key === "no_tests" && factor.triggered);
  const primaryConcern = testsMissing ? "Implementation changed without corresponding test updates." : result.heuristics.factors.find((factor) => factor.triggered)?.reason || "Review the evidence-backed findings before merging.";
  const apiChanged = Boolean(report.engineering_metrics?.public_apis_modified);
  const sensitive = paths.some((path) => /auth|secret|credential|token/.test(path));
  const requiredActions = [
    ...(testsMissing ? ["Add regression tests for the changed implementation paths."] : []),
    ...(paths.some((path) => path.includes("report") || path.includes("render")) ? ["Validate rendered Markdown output against a representative pull request."] : []),
    ...(workflowChanged ? ["Dry-run the modified GitHub Actions workflow on a sample pull request."] : []),
  ].slice(0, 3);
  const perspectives = [
    { name: "Backend", status: backendChanged ? "WARN" : "PASS", reason: backendChanged ? "Report rendering or backend implementation changed; review the generated Markdown output." : "No backend implementation files changed." },
    { name: "Security", status: sensitive ? "WARN" : "PASS", reason: sensitive ? "Security-sensitive paths changed; verify the diff." : "No authentication, secrets, or credential paths changed." },
    { name: "QA", status: testsMissing ? "WARN" : "PASS", reason: testsMissing ? "Implementation changed without test updates; add regression coverage." : "Test coverage was updated or no implementation path changed." },
    { name: "SRE", status: workflowChanged ? "WARN" : "PASS", reason: workflowChanged ? "GitHub Actions workflow changed; dry-run it on a sample pull request." : "No CI/CD or deployment configuration changed." },
    { name: "API", status: apiChanged ? "WARN" : "PASS", reason: apiChanged ? "Public API routes changed; verify contract compatibility." : "No public API interface changes were detected." },
  ];
  return <div className="flex flex-col gap-6">
    <section className="rounded-lg border border-steel bg-panel p-5 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="font-mono text-xs text-fog">{pr.owner}/{pr.repo} · #{pr.number}</p><h2 className="font-display text-base font-semibold text-paper">{pr.title}</h2></div>
        <span className={`rounded-full px-3 py-1 font-mono text-xs font-semibold ${badgeFor(result) === "Do Not Merge" ? "bg-risk-high/15 text-risk-high" : badgeFor(result) === "Ready" ? "bg-risk-low/15 text-risk-low" : "bg-risk-medium/15 text-risk-medium"}`}>{badgeFor(result)}</span>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-3 border-t border-steel pt-4 sm:grid-cols-5">
        <Stat label="Decision" value={report.decision} /><Stat label="Risk" value={ai.overall_risk} /><Stat label="Confidence" value={confidence} /><Stat label="Readiness" value={`${readiness?.score ?? "n/a"}/100`} /><Stat label="Deployment" value={deployment} />
      </div>
      <p className="mt-4 border-t border-steel pt-3 text-sm text-fog"><span className="font-semibold text-paper">Primary concern:</span> {primaryConcern}</p>
    </section>

    <Card title="Executive summary" eyebrow="What changed, main risk, merge decision">
      <p className="text-sm leading-relaxed text-paper">{truncateWords(report.executive_summary || report.summary || ai.summary)}</p>
    </Card>

    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Card title="Top findings" eyebrow="Evidence-backed · top 5">
        {findings.length ? <ul className="flex flex-col gap-3">{findings.map((item, i) => <li key={`${item.file_path}-${i}`} className="border-b border-steel/60 pb-3 last:border-0 last:pb-0"><div className="flex items-center gap-2"><Severity level={item.severity} /><code className="truncate text-xs text-paper">{item.file_path}</code></div><p className="mt-1 text-xs text-fog">{item.explanation}</p><p className="mt-1 text-xs text-fog"><span className="text-paper">Evidence:</span> <code>{item.file_path}</code></p></li>)}</ul> : <p className="text-sm text-fog">No evidence-backed findings were produced.</p>}
      </Card>
      <Card title="Highest-risk files" eyebrow="Top 3 by risk">
        <div className="flex flex-col gap-3">{fileRisks.map((file) => <div key={file.filename} className="border-b border-steel/60 pb-3 last:border-0 last:pb-0"><div className="flex items-center justify-between gap-2"><code className="truncate text-xs text-paper">{file.filename}</code><Severity level={file.risk} /></div><p className="mt-1 text-xs text-fog">{file.reason}</p><p className="mt-1 text-xs text-paper">Action: {actionFor(file.filename)}</p></div>)}{!fileRisks.length && <p className="text-sm text-fog">No files were individually flagged.</p>}</div>
      </Card>
    </div>

    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Card title="Required before merge" eyebrow="Actionable reviewer checklist">
        {requiredActions.length ? <ul className="flex flex-col gap-2">{requiredActions.map((action) => <li key={action} className="flex gap-2 text-sm text-fog"><span className="text-paper">□</span>{action}</li>)}</ul> : <p className="text-sm text-fog">No additional mandatory action identified from available evidence.</p>}
      </Card>
      <Card title="Merge readiness" eyebrow="Risk + evidence + tests + documentation">
        {readiness ? <><ProductionReadinessGauge readiness={readiness} /><p className="mt-3 text-xs text-fog">Derived from risk, evidence quality, test coverage, and documentation completeness.</p></> : <p className="text-sm text-fog">Readiness could not be calculated from the available evidence.</p>}
      </Card>
    </div>

    <Card title="Review perspectives" eyebrow="Specialist outcome">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">{perspectives.map((perspective) => <div key={perspective.name} className="rounded-md border border-steel bg-raised p-3"><div className="flex justify-between gap-2"><span className="text-xs font-semibold text-paper">{perspective.name}</span><span className={perspective.status === "WARN" ? "font-mono text-xs text-risk-medium" : "font-mono text-xs text-risk-low"}>{perspective.status}</span></div><p className="mt-1 text-xs text-fog">{perspective.reason}</p></div>)}</div>
    </Card>

    <Collapsible header={<span className="font-display text-sm font-semibold text-paper">Evidence &amp; scoring</span>}>
      <div className="flex flex-col gap-6"><Card title="Risk breakdown" eyebrow="Raw category evidence"><CategoryBreakdown categories={report.risk_categories} /></Card><Card title="Detailed review reasoning" eyebrow="Expandable specialist detail"><AgentPipelinePanel decisions={report.agent_decisions} /></Card>{report.engineering_metrics && <Card title="Engineering metrics" eyebrow="Deterministic details"><EngineeringMetricsCard metrics={report.engineering_metrics} /></Card>}<Card title="Repository evidence" eyebrow="Retrieved documentation"><CitationsList rag={result.rag} /></Card></div>
    </Collapsible>
  </div>;
}

function Stat({ label, value }: { label: string; value: string }) { return <div><p className="font-mono text-[10px] uppercase tracking-wider text-fog">{label}</p><p className="mt-1 text-sm font-semibold text-paper">{value}</p></div>; }
function Severity({ level }: { level: RiskLevel }) { const label = level === "HIGH" ? "Critical" : level === "MEDIUM" ? "Warning" : "Info"; const color = level === "HIGH" ? "bg-risk-high/15 text-risk-high" : level === "MEDIUM" ? "bg-risk-medium/15 text-risk-medium" : "bg-risk-low/15 text-risk-low"; return <span className={`shrink-0 rounded px-2 py-0.5 font-mono text-[10px] font-semibold ${color}`}>{label}</span>; }
