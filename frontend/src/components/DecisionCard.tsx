import type { AnalyzeResponse } from "../types";

const DECISION_STYLE: Record<string, string> = {
  BLOCK: "border-risk-high bg-risk-high/10 text-risk-high",
  NEEDS_REVIEW: "border-amber/50 bg-amber/10 text-amber",
  ALLOW: "border-risk-low bg-risk-low/10 text-risk-low",
};

const RISK_COLOR: Record<string, string> = {
  LOW: "text-risk-low",
  MEDIUM: "text-risk-medium",
  HIGH: "text-risk-high",
};

export default function DecisionCard({ result }: { result: AnalyzeResponse }) {
  const { report } = result;
  const releaseRisk = report.release_risk ?? result.ai.overall_risk;
  const complexity = report.review_complexity;
  const evidenceTier = report.confidence_explanation?.level ?? "MEDIUM";
  const readiness = report.production_readiness?.score ?? Math.max(0, 100 - report.risk_score);
  const disagreement = report.llm_disagreement;

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-steel bg-panel p-6 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-fog">PR Sentinel</p>
          <p
            className={`mt-2 font-display text-4xl font-bold tracking-tight ${
              DECISION_STYLE[report.decision]?.split(" ").pop() ?? "text-paper"
            }`}
          >
            {report.decision.replace("_", " ")}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm sm:grid-cols-4">
          <div>
            <p className="font-mono text-[10px] uppercase text-fog">Release Risk</p>
            <p className={`font-semibold ${RISK_COLOR[releaseRisk]}`}>{releaseRisk}</p>
          </div>
          <div>
            <p className="font-mono text-[10px] uppercase text-fog">Review Complexity</p>
            <p className={`font-semibold ${RISK_COLOR[complexity?.level ?? "MEDIUM"]}`}>
              {complexity?.level ?? "—"}
            </p>
          </div>
          <div>
            <p className="font-mono text-[10px] uppercase text-fog">Merge Readiness</p>
            <p className="font-semibold text-paper">{readiness}/100</p>
          </div>
          <div>
            <p className="font-mono text-[10px] uppercase text-fog">Evidence Confidence</p>
            <p className="font-semibold text-paper">{evidenceTier}</p>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-steel/80 bg-ink/40 px-4 py-3 text-sm text-fog">
        <span className="font-semibold text-paper">Policy enforced deterministically.</span> The LLM can
        explain risk but cannot override the release policy.
      </div>

      {disagreement?.detected && (
        <div className="rounded-lg border border-amber/40 bg-amber/10 px-4 py-3 text-sm">
          <p className="font-semibold text-amber">⚠ Deterministic Override</p>
          <p className="mt-1 text-fog">
            LLM assessment: <span className="font-mono text-paper">{disagreement.llm_risk}</span> ·
            Deterministic assessment:{" "}
            <span className="font-mono text-paper">{disagreement.deterministic_risk}</span> · Final
            decision: <span className="font-mono font-semibold text-paper">{report.decision}</span>
          </p>
        </div>
      )}

      {(result.policy_note || !result.ai_enabled) && (
        <p className="text-xs text-amber">
          {result.policy_note ??
            "AI synthesis unavailable. Final release decision was produced by the deterministic policy engine."}
        </p>
      )}
    </div>
  );
}
