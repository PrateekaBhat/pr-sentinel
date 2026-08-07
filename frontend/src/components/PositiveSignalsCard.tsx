import type { PositiveSignal } from "../types";

interface Props {
  signals: PositiveSignal[];
}

export default function PositiveSignalsCard({ signals }: Props) {
  if (!signals.length) return null;

  return (
    <ul className="flex flex-col gap-2">
      {signals.map((signal, i) => (
        <li
          key={`${signal.label}-${i}`}
          className="flex items-start gap-2.5 rounded-md border border-emerald-500/20 bg-emerald-500/5 px-3 py-2.5"
        >
          <span className="mt-0.5 shrink-0 text-emerald-400" aria-hidden="true">
            ✓
          </span>
          <div className="flex flex-col gap-0.5">
            <span className="text-sm text-paper">{signal.label}</span>
            <span className="text-xs text-fog">{signal.reason}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
