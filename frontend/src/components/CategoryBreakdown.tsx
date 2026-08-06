import Collapsible from "./Collapsible";
import type { EvidenceItem, RiskCategory, RiskLevel } from "../types";

const STATUS_COLOR: Record<RiskLevel, string> = {
  LOW: "text-risk-low",
  MEDIUM: "text-risk-medium",
  HIGH: "text-risk-high",
};

const STATUS_BAR: Record<RiskLevel, string> = {
  LOW: "bg-risk-low",
  MEDIUM: "bg-risk-medium",
  HIGH: "bg-risk-high",
};

const BADGE_BG: Record<RiskLevel, string> = {
  LOW: "bg-risk-low/15 text-risk-low",
  MEDIUM: "bg-risk-medium/15 text-risk-medium",
  HIGH: "bg-risk-high/15 text-risk-high",
};

function EvidenceRow({ item }: { item: EvidenceItem }) {
  return (
    <div className="rounded-md border border-steel/70 bg-panel px-3 py-2.5">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <code className="truncate font-mono text-xs text-paper">{item.file_path}</code>
        <div className="flex shrink-0 items-center gap-1.5">
          <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold ${BADGE_BG[item.severity]}`}>
            {item.severity}
          </span>
          <span className="font-mono text-[10px] text-fog">{item.confidence}% conf.</span>
        </div>
      </div>
      <p className="text-xs leading-relaxed text-fog">{item.explanation}</p>
      {item.snippet && (
        <pre className="mt-1.5 overflow-x-auto rounded bg-ink px-2 py-1.5 font-mono text-[11px] text-fog">
          {item.snippet}
        </pre>
      )}
      <p className="mt-1.5 text-xs text-amber">↳ {item.recommended_action}</p>
    </div>
  );
}

function CategoryRow({ category }: { category: RiskCategory }) {
  const header = (
    <div className="flex flex-wrap items-center gap-3">
      <span className="min-w-[9rem] font-display text-sm font-semibold text-paper">{category.category}</span>
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-steel/60">
        <div
          className={`h-full rounded-full ${STATUS_BAR[category.status]}`}
          style={{ width: `${Math.max(4, category.score)}%` }}
        />
      </div>
      <span className={`font-mono text-xs font-semibold ${STATUS_COLOR[category.status]}`}>
        {category.status} · {category.score}/100
      </span>
      <span className="ml-auto font-mono text-[11px] text-fog">
        {category.evidence.length} evidence item{category.evidence.length === 1 ? "" : "s"}
      </span>
    </div>
  );

  return (
    <Collapsible header={header}>
      <p className="mb-2 text-xs text-fog">{category.summary}</p>
      {category.evidence.length === 0 ? (
        <p className="text-xs text-fog">No evidence in this category.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {category.evidence.map((item, i) => (
            <EvidenceRow key={i} item={item} />
          ))}
        </div>
      )}
    </Collapsible>
  );
}

export default function CategoryBreakdown({ categories }: { categories: RiskCategory[] }) {
  if (categories.length === 0) {
    return <p className="text-sm text-fog">No category breakdown available for this analysis.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      {categories.map((c) => (
        <CategoryRow key={c.category} category={c} />
      ))}
    </div>
  );
}
