import type { ReviewQueueItem } from "../types";

export default function ReviewQueueCard({ items }: { items: ReviewQueueItem[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-fog">No prioritized review queue for this change.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      {items.map((item) => (
        <div key={item.filename} className="rounded-lg border border-steel bg-ink/30 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded bg-steel px-2 py-0.5 font-mono text-[10px] font-bold text-paper">
              {item.priority}
            </span>
            <code className="text-xs text-paper">{item.filename}</code>
            <span className="text-xs text-fog">· {item.role}</span>
            <span className="ml-auto font-mono text-[10px] text-fog">~{item.estimated_minutes} min</span>
          </div>
          <p className="mt-2 text-xs text-fog">{item.why_it_matters}</p>
          <p className="mt-1 text-[11px] text-fog">
            Validate: {item.suggested_validation}
          </p>
        </div>
      ))}
    </div>
  );
}
