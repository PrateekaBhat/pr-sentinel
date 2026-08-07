import type { UncertaintyItem } from "../types";

interface Props {
  items: UncertaintyItem[];
}

export default function UncertaintyCard({ items }: Props) {
  if (!items.length) return null;

  return (
    <ul className="flex flex-col gap-2">
      {items.map((item, i) => (
        <li
          key={`${item.area}-${i}`}
          className="flex items-start gap-2.5 rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2.5"
        >
          <span className="mt-0.5 shrink-0 text-amber-400" aria-hidden="true">
            ?
          </span>
          <div className="flex flex-col gap-0.5">
            <span className="text-sm text-paper">{item.area}</span>
            <span className="text-xs text-fog">{item.reason}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
