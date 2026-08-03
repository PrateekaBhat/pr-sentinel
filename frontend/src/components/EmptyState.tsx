export default function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-steel py-20 text-center">
      <span className="font-mono text-3xl text-fog">◈</span>
      <p className="max-w-sm text-sm text-fog">
        Paste a public GitHub pull request URL above, or pick a curated example, to see its
        deployment risk, rollout recommendation, and test coverage gaps.
      </p>
    </div>
  );
}
