import Collapsible from "./Collapsible";
import type { AgentDecision } from "../types";

const AGENT_ICON: Record<string, string> = {
  security: "🔒",
  performance: "⚡",
  database: "🗄",
  api: "🔌",
  tests: "✅",
};

function decisionColor(decision: string): string {
  if (decision.startsWith("Concerns")) return "text-risk-medium";
  if (decision.startsWith("Skipped")) return "text-fog";
  return "text-risk-low";
}

export default function AgentPipelinePanel({ decisions }: { decisions: AgentDecision[] }) {
  if (decisions.length === 0) {
    return <p className="text-sm text-fog">No agent execution data available for this analysis.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-fog">
        Each specialist agent only reviews files in its own domain. The coordinator agent then
        synthesizes their output into the executive summary and risk breakdown above.
      </p>
      {decisions.map((d) => {
        const header = (
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm">{AGENT_ICON[d.agent] ?? "•"}</span>
            <span className="min-w-[7rem] font-display text-sm font-semibold text-paper">{d.label}</span>
            <span className={`font-mono text-xs font-semibold ${decisionColor(d.decision)}`}>{d.decision}</span>
            <span className="ml-auto font-mono text-[11px] text-fog">
              {d.confidence}% conf. · {d.execution_time_ms}ms
            </span>
          </div>
        );
        return (
          <Collapsible key={d.agent} header={header}>
            <p className="text-xs leading-relaxed text-fog">{d.reasoning || "No further reasoning recorded."}</p>
          </Collapsible>
        );
      })}
    </div>
  );
}
