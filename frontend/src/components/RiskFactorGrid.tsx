import type { RiskFactorFlag } from "../types";

export default function RiskFactorGrid({ factors }: { factors: RiskFactorFlag[] }) {
  if (factors.length === 0) {
    return <p className="text-sm text-fog">No notable risk factors detected.</p>;
  }

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {factors.map((f) => (
        <div
          key={f.key}
          className="flex items-center gap-2 rounded-md border border-steel bg-raised px-3 py-2"
        >
          <span
            className={`font-mono text-sm ${f.passed ? "text-risk-low" : "text-risk-high"}`}
          >
            {f.passed ? "✓" : "✗"}
          </span>
          <span className="text-sm text-paper">{f.label}</span>
        </div>
      ))}
    </div>
  );
}
