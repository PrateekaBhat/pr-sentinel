import type { ChecklistItem } from "../types";

interface Props {
  items: ChecklistItem[];
}

export default function OperationalChecklistCard({ items }: Props) {
  if (!items.length) return null;

  return (
    <ul className="flex flex-col gap-2">
      {items.map((item, i) => (
        <li
          key={`${item.task}-${i}`}
          className="flex items-start gap-2.5 rounded-md border border-steel bg-raised px-3 py-2.5"
        >
          <span className="mt-0.5 h-4 w-4 shrink-0 rounded border border-fog" aria-hidden="true" />
          <div className="flex flex-col gap-0.5">
            <span className="text-sm text-paper">{item.task}</span>
            <span className="text-xs text-fog">{item.reason}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
