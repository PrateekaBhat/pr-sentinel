import type { AgentDecision, SpecialistRoutingEntry } from "../types";

const AGENT_ICON: Record<string, string> = {
  security: "🔒",
  performance: "⚡",
  database: "🗄",
  api: "🔌",
  tests: "✅",
};

function decisionColor(decision: string, status?: string): string {
  if (status === "EXECUTED" && decision.startsWith("Concerns")) return "text-risk-medium";
  if (status === "SKIPPED" || decision.startsWith("SKIPPED")) return "text-fog";
  if (status === "EXECUTED") return "text-risk-low";
  if (decision.startsWith("Concerns")) return "text-risk-medium";
  if (decision.startsWith("Skipped") || decision.startsWith("SKIPPED")) return "text-fog";
  return "text-risk-low";
}

export default function AgentPipelinePanel({
  decisions,
  routing = [],
}: {
  decisions: AgentDecision[];
  routing?: SpecialistRoutingEntry[];
}) {
  if (decisions.length === 0 && routing.length === 0) {
    return <p className="text-sm text-fog">No specialist routing data available for this analysis.</p>;
  }

  if (routing.length > 0) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-xs text-fog">
          Specialists run only when relevant files are detected. Skipped agents make no LLM call.
        </p>
        {routing.map((entry) => (
          <div key={entry.domain} className="rounded-lg border border-steel px-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <span>{AGENT_ICON[entry.domain] ?? "•"}</span>
              <span className="font-display text-sm font-semibold text-paper">{entry.label}</span>
              <span
                className={`font-mono text-xs font-bold ${
                  entry.status === "EXECUTED" ? "text-risk-low" : "text-fog"
                }`}
              >
                {entry.status}
              </span>
              {entry.duration_ms > 0 && (
                <span className="ml-auto font-mono text-[11px] text-fog">{entry.duration_ms}ms</span>
              )}
            </div>
            <p className="mt-1 text-xs text-fog">
              Trigger: {entry.trigger} · Files: {entry.files_count}
              {entry.llm_call_made ? "" : " · LLM call: not made"}
            </p>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-fog">
        Each specialist agent only reviews files in its own domain.
      </p>
      {decisions.map((d) => (
        <div key={d.agent} className="rounded-lg border border-steel px-3 py-2">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm">{AGENT_ICON[d.agent] ?? "•"}</span>
            <span className="min-w-[7rem] font-display text-sm font-semibold text-paper">{d.label}</span>
            <span className={`font-mono text-xs font-semibold ${decisionColor(d.decision)}`}>{d.decision}</span>
            <span className="ml-auto font-mono text-[11px] text-fog">{d.execution_time_ms}ms</span>
          </div>
          <p className="mt-1 text-xs text-fog">{d.reasoning || "No further reasoning recorded."}</p>
        </div>
      ))}
    </div>
  );
}
