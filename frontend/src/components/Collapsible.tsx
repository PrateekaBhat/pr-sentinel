import { useState, type ReactNode } from "react";

interface Props {
  header: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}

/** A single collapsible engineering-report row: click the header to expand the
 * evidence/reasoning underneath it. Used throughout the risk dashboard so a dense
 * report stays scannable while still exposing full detail on demand. */
export default function Collapsible({ header, children, defaultOpen = false, className = "" }: Props) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={`rounded-md border border-steel bg-raised ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left"
      >
        <div className="min-w-0 flex-1">{header}</div>
        <span
          className={`shrink-0 font-mono text-xs text-fog transition-transform ${open ? "rotate-90" : ""}`}
        >
          ▶
        </span>
      </button>
      {open && <div className="border-t border-steel px-3 py-3">{children}</div>}
    </div>
  );
}
