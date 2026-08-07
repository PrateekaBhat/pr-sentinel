import type { ArchitecturalImpact } from "../types";

export default function ArchitecturalImpactCard({ impact }: { impact: ArchitecturalImpact }) {
  return (
    <div className="flex flex-col gap-3">
      {impact.affected_subsystems.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {impact.affected_subsystems.map((s) => (
            <span
              key={s}
              className="rounded-full border border-steel bg-raised px-2.5 py-1 font-mono text-[11px] text-paper"
            >
              {s}
            </span>
          ))}
        </div>
      )}
      <p className="text-sm leading-relaxed text-fog">
        {impact.narrative || "No clearly affected subsystems were detected."}
      </p>
    </div>
  );
}
