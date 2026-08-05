import type { AgentFinding } from "../types";

const AGENT_ICON: Record<string, string> = {
  security: "🔒",
  performance: "⚡",
  database: "🗄",
  api: "🔌",
  tests: "✅",
};

export default function AgentFindingsPanel({ agents }: { agents: AgentFinding[] }) {
  if (agents.length === 0) {
    return <p className="text-sm text-fog">No agent findings available for this analysis.</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {agents.map((agent) => (
        <div
          key={agent.agent}
          className={`rounded-md border px-3 py-3 ${
            agent.applicable
              ? "border-steel bg-raised"
              : "border-steel/50 bg-raised/40 opacity-60"
          }`}
        >
          <div className="mb-1.5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm">{AGENT_ICON[agent.agent] ?? "•"}</span>
              <span className="font-display text-sm font-semibold text-paper">{agent.label}</span>
            </div>
            <span
              className={`rounded px-2 py-0.5 font-mono text-[10px] font-semibold ${
                agent.applicable
                  ? "bg-risk-medium/15 text-risk-medium"
                  : "bg-steel/60 text-fog"
              }`}
            >
              {agent.applicable ? `${agent.files_reviewed.length} file(s)` : "not applicable"}
            </span>
          </div>

          {agent.applicable && agent.findings.length > 0 && (
            <ul className="mb-1.5 flex flex-col gap-1">
              {agent.findings.map((f, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-paper">
                  <span className="mt-0.5 text-fog">›</span>
                  {f}
                </li>
              ))}
            </ul>
          )}

          <p className="text-xs italic text-fog">{agent.risk_note}</p>
        </div>
      ))}
    </div>
  );
}
