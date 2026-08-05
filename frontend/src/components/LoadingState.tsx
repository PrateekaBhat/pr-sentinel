const STEPS = [
  "Fetching PR metadata & diff from GitHub…",
  "Running deterministic risk heuristics…",
  "Sending diff to Llama for analysis…",
  "Assembling risk report…",
];

export default function LoadingState() {
  return (
    <div className="flex flex-col items-center gap-4 rounded-lg border border-steel bg-panel py-20 text-center shadow-panel">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-steel border-t-risk-medium" />
      <div className="flex flex-col gap-1 font-mono text-xs text-fog">
        {STEPS.map((step) => (
          <span key={step}>{step}</span>
        ))}
      </div>
    </div>
  );
}
