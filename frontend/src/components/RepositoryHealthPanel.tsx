import type { RepositoryHealth } from "../types";

interface Props {
  health: RepositoryHealth;
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col gap-1 rounded-md border border-steel bg-raised px-3 py-2.5">
      <span className="text-xs text-fog">{label}</span>
      <span className="font-mono text-sm font-semibold text-paper">{value}</span>
    </div>
  );
}

function RiskSparkline({ trend }: { trend: RepositoryHealth["risk_trend"] }) {
  if (trend.length < 2) {
    return <p className="text-xs text-fog">Not enough history yet for a trend line.</p>;
  }
  const w = 320;
  const h = 60;
  const pad = 4;
  const max = 100;
  const step = (w - pad * 2) / (trend.length - 1);
  const points = trend.map((t, i) => {
    const x = pad + i * step;
    const y = h - pad - (t.risk_score / max) * (h - pad * 2);
    return `${x},${y}`;
  });
  const color = trend[trend.length - 1].risk_score >= 60 ? "#E5484D" : trend[trend.length - 1].risk_score >= 35 ? "#F5A623" : "#3DD68C";

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full max-w-sm">
      <polyline points={points.join(" ")} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      {points.map((p, i) => {
        const [x, y] = p.split(",").map(Number);
        return <circle key={i} cx={x} cy={y} r={2.5} fill={color} />;
      })}
    </svg>
  );
}

export default function RepositoryHealthPanel({ health }: Props) {
  if (health.analyses_count === 0) {
    return <p className="text-sm text-fog">No history yet for this repository — this looks like the first analysis.</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Analyses" value={health.analyses_count} />
        <Stat label="Avg risk score" value={health.average_risk_score} />
        <Stat label="Avg confidence" value={`${health.average_confidence}%`} />
        <Stat label="Avg files changed" value={health.average_files_changed} />
      </div>

      <div>
        <p className="mb-1.5 text-xs text-fog">Risk score trend (oldest → newest)</p>
        <RiskSparkline trend={health.risk_trend} />
      </div>

      {health.top_recurring_categories.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs text-fog">Top recurring risk categories</p>
          <div className="flex flex-wrap gap-2">
            {health.top_recurring_categories.map(([category, count]) => (
              <span
                key={category}
                className="rounded-md border border-steel bg-raised px-2.5 py-1 text-xs text-paper"
              >
                {category} <span className="text-fog">×{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {Object.keys(health.deployment_distribution).length > 0 && (
        <div>
          <p className="mb-1.5 text-xs text-fog">Deployment recommendation distribution</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(health.deployment_distribution).map(([strategy, count]) => (
              <span
                key={strategy}
                className="rounded-md border border-steel bg-raised px-2.5 py-1 text-xs text-paper"
              >
                {strategy} <span className="text-fog">×{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
