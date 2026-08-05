import { FormEvent, useState } from "react";

interface Props {
  onAnalyze: (prUrl: string) => void;
  loading: boolean;
}

export default function RepoInput({ onAnalyze, loading }: Props) {
  const [value, setValue] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    const fullUrl = trimmed.startsWith("http") ? trimmed : `https://github.com/${trimmed}`;
    onAnalyze(fullUrl);
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row">
      <div className="flex flex-1 items-center gap-2 rounded-lg border border-steel bg-panel px-4 py-3 shadow-panel focus-within:border-risk-medium/60">
        <span className="font-mono text-sm text-fog">github.com/</span>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="owner/repo/pull/12345 — or paste a full PR URL"
          className="w-full bg-transparent font-mono text-sm text-paper placeholder:text-fog/60 focus:outline-none"
          disabled={loading}
        />
      </div>
      <button
        type="submit"
        disabled={loading || !value.trim()}
        className="rounded-lg bg-risk-medium px-6 py-3 font-display text-sm font-semibold text-ink transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {loading ? "Analyzing…" : "Analyze"}
      </button>
    </form>
  );
}
