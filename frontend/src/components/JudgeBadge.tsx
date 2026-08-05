import type { JudgeVerdict } from "../types";

export default function JudgeBadge({ judge }: { judge: JudgeVerdict | null | undefined }) {
  if (!judge) return null;

  return (
    <div className="group relative">
      <span
        className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1 font-mono text-[11px] ${
          judge.grounded
            ? "border-risk-low/40 bg-risk-low/10 text-risk-low"
            : "border-risk-high/40 bg-risk-high/10 text-risk-high"
        }`}
      >
        {judge.grounded ? "✓ Judge: grounded" : `⚠ Judge: ${judge.issues.length} ungrounded claim(s)`}
      </span>
      <div className="pointer-events-none absolute right-0 z-10 mt-2 w-72 rounded-md border border-steel bg-panel p-3 text-xs text-fog opacity-0 shadow-panel transition group-hover:opacity-100">
        <p className="mb-1 text-paper">{judge.notes}</p>
        {judge.issues.length > 0 && (
          <ul className="flex flex-col gap-1">
            {judge.issues.map((issue, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <span className="text-risk-high">·</span>
                {issue}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
