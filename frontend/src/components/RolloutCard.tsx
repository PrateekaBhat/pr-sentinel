interface Props {
  strategy: string;
  reason: string;
  rollbackRequired: boolean;
}

export default function RolloutCard({ strategy, reason, rollbackRequired }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="font-display text-xl font-semibold text-paper">{strategy}</span>
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
    </div>
  );
}
