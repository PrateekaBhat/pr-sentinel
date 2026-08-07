import type { ProductionReadinessScore } from "../types";

interface Props {
  readiness: ProductionReadinessScore;
}

function colorFor(score: number): string {
  if (score >= 80) return "#3DD68C";
  if (score >= 55) return "#F5A623";
  return "#E5484D";
}

export default function ProductionReadinessGauge({ readiness }: Props) {
  const color = colorFor(readiness.score);
  const circumference = 2 * Math.PI * 52;
  const offset = circumference * (1 - readiness.score / 100);

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
      <div className="relative flex h-32 w-32 shrink-0 items-center justify-center self-center">
        <svg viewBox="0 0 120 120" className="h-32 w-32 -rotate-90">
          <circle cx="60" cy="60" r="52" fill="none" stroke="#22304A" strokeWidth="10" />
          <circle
            cx="60"
            cy="60"
            r="52"
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="absolute flex flex-col items-center">
          <span className="font-display text-2xl font-semibold tracking-tight" style={{ color }}>
            {readiness.score}
          </span>
          <span className="text-[10px] text-fog">/ 100</span>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="font-display text-sm font-semibold tracking-tight" style={{ color }}>
          {readiness.label}
        </span>
        {readiness.deductions.length > 0 ? (
          <ul className="flex flex-col gap-1">
            {readiness.deductions.map((d, i) => (
              <li key={i} className="text-xs text-fog">
                {d}
              </li>
            ))}
          </ul>
        ) : (
          <span className="text-xs text-fog">No readiness deductions.</span>
        )}
      </div>
    </div>
  );
}
