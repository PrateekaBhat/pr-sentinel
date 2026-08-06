import type { DeploymentRecommendation } from "../types";

const STRATEGY_COLOR: Record<string, string> = {
  Standard: "text-risk-low",
  Canary: "text-risk-medium",
  "Blue/Green": "text-risk-medium",
  "Manual Approval": "text-risk-high",
};

interface Props {
  strategy: string;
  reason: string;
  rollbackRequired: boolean;
  alternativesConsidered?: string[];
}

export default function RolloutCard({ strategy, reason, rollbackRequired, alternativesConsidered = [] }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className={`font-display text-xl font-semibold ${STRATEGY_COLOR[strategy] ?? "text-paper"}`}>
          {strategy}
        </span>
        <span
          className={`rounded-full px-2.5 py-1 font-mono text-[11px] font-semibold ${
            rollbackRequired
              ? "bg-risk-high/15 text-risk-high"
              : "bg-risk-low/15 text-risk-low"
          }`}
        >
          {rollbackRequired ? "Rollback plan required" : "No rollback plan needed"}
        </span>
      </div>
      <p className="text-sm leading-relaxed text-fog">{reason}</p>

      {alternativesConsidered.length > 0 && (
        <div className="border-t border-steel pt-3">
          <p className="mb-1.5 font-mono text-[11px] uppercase tracking-wider text-fog">
            Alternatives considered
          </p>
          <ul className="flex flex-col gap-1">
            {alternativesConsidered.map((alt) => (
              <li key={alt} className="flex items-start gap-1.5 text-xs text-fog">
                <span className="mt-0.5 text-steel">–</span>
                {alt}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function DeploymentRecommendationCard({ recommendation }: { recommendation: DeploymentRecommendation }) {
  return (
    <RolloutCard
      strategy={recommendation.strategy}
      reason={recommendation.reason}
      rollbackRequired={recommendation.rollback_required}
      alternativesConsidered={recommendation.alternatives_considered}
    />
  );
}
