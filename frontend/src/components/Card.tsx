import type { ReactNode } from "react";

interface Props {
  title: string;
  eyebrow?: string;
  children: ReactNode;
  className?: string;
}

export default function Card({ title, eyebrow, children, className = "" }: Props) {
  return (
    <section
      className={`rounded-lg border border-steel bg-panel p-5 shadow-panel ${className}`}
    >
      {eyebrow && (
        <p className="mb-1 font-mono text-[11px] uppercase tracking-wider text-fog">
          {eyebrow}
        </p>
      )}
      <h2 className="mb-3 font-display text-sm font-semibold text-paper">{title}</h2>
      {children}
    </section>
  );
}
