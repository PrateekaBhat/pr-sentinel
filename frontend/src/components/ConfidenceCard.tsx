import type { ConfidenceExplanation } from "../types";

function ConfidenceBar({ score }: { score: number }) {
  const color = score >= 70 ? "bg-risk-low" : score >= 40 ? "bg-risk-medium" : "bg-risk-high";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-steel">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
      </div>
      <span className="font-mono text-xs text-fog">{score}%</span>
    </div>
  );
}

export default function ConfidenceCard({ confidence }: { confidence: ConfidenceExplanation }) {
  const checks = confidence.checks && confidence.checks.length > 0
    ? confidence.checks
    : [
        { key: "repo_context", label: "Repository context (RAG) was available", passed: confidence.repository_context_available },
        { key: "llm_agreement", label: "LLM and heuristic analyses agree", passed: confidence.llm_heuristic_agreement },
      ];
  const based_on = checks.filter((check) => check.passed);
  const missing = checks.filter((check) => !check.passed);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline gap-2">
        <span className="font-display text-2xl font-semibold text-paper">{confidence.level ?? "MEDIUM"}</span>
        <span className="rounded px-2 py-0.5 font-mono text-[11px] font-semibold bg-steel/50 text-fog">
          Evidence Confidence
        </span>
      </div>
      <ConfidenceBar score={confidence.score} />
      <p className="text-sm leading-relaxed text-fog">{confidence.narrative}</p>
      <div className="flex flex-col gap-3 border-t border-steel pt-3">
        {based_on.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="font-mono text-[11px] uppercase tracking-wide text-fog/70">Based on</span>
            {based_on.map((check) => (
              <div key={check.key} className="flex items-center gap-2">
                <span className="font-mono text-sm text-risk-low">✓</span>
                <span className="text-xs text-fog">{check.label}</span>
              </div>
            ))}
          </div>
        )}
        {missing.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="font-mono text-[11px] uppercase tracking-wide text-fog/70">Missing</span>
            {missing.map((check) => (
              <div key={check.key} className="flex items-center gap-2">
                <span className="font-mono text-sm text-risk-high">✗</span>
                <span className="text-xs text-fog">{check.label}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
