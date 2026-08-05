import type { DemoSummary } from "../types";

interface Props {
  demos: DemoSummary[];
  onSelect: (id: string) => void;
  activeId?: string;
}

export default function DemoGallery({ demos, onSelect, activeId }: Props) {
  if (demos.length === 0) return null;

  return (
    <div>
      <p className="mb-2 font-mono text-xs uppercase tracking-wider text-fog">
        Or try a curated example
      </p>
      <div className="flex flex-wrap gap-2">
        {demos.map((demo) => (
          <button
            key={demo.id}
            onClick={() => onSelect(demo.id)}
            className={`rounded-md border px-3 py-2 text-left text-xs transition ${
              activeId === demo.id
                ? "border-risk-medium/70 bg-risk-medium/10 text-paper"
                : "border-steel bg-panel text-fog hover:border-steel/80 hover:text-paper"
            }`}
          >
            <div className="font-mono text-[11px] text-fog">
              {demo.repo}#{demo.pr_number}
            </div>
            <div className="mt-0.5 max-w-[220px] truncate">{demo.tagline}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
