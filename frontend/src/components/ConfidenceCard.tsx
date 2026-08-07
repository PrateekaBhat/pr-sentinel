import type { ConfidenceExplanation } from "../types";

function CheckRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`font-mono text-sm ${ok ? "text-risk-low" : "text-risk-high"}`}>{ok ? "✓" : "✗"}</span>
      <span className="text-xs text-fog">{label}</span>
    </div>
  );
}

export default function ConfidenceCard({ confidence }: { confidence: ConfidenceExplanation }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline gap-2">
        <span className="font-display text-2xl font-semibold text-paper">{confidence.score}%</span>
        <span
          className={`rounded px-2 py-0.5 font-mono text-[11px] font-semibold ${
            confidence.evidence_completeness === "complete"
              ? "bg-risk-low/15 text-risk-low"
              : "bg-risk-medium/15 text-risk-medium"
          }`}
        >
          {confidence.evidence_completeness} evidence
        </span>
      </div>
      <p className="text-sm leading-relaxed text-fog">{confidence.narrative}</p>
      <div className="flex flex-col gap-1.5 border-t border-steel pt-3">
        {confidence.checks && confidence.checks.length > 0 ? (
          confidence.checks.map((check) => <CheckRow key={check.key} ok={check.passed} label={check.label} />)
        ) : (
          <>
            <CheckRow ok={confidence.repository_context_available} label="Repository context (RAG) was available" />
            <CheckRow ok={confidence.llm_heuristic_agreement} label="LLM and heuristic analyses agree" />
          </>
        )}
      </div>
    </div>
  );
}
