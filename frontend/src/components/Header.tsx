export default function Header() {
  return (
    <header className="border-b border-steel/60">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-md border border-risk-medium/50 bg-risk-medium/10">
            <span className="font-mono text-sm font-semibold text-risk-medium">◈</span>
          </div>
          <div>
            <h1 className="font-display text-lg font-semibold tracking-tight text-paper">
              PR Sentinel
            </h1>
            <p className="text-xs text-fog">Risk analysis before you merge</p>
          </div>
        </div>
        <a
          href="https://github.com"
          className="hidden rounded-md border border-steel px-3 py-1.5 font-mono text-xs text-fog transition hover:border-risk-medium/60 hover:text-paper sm:block"
        >
          v0.1 · MVP
        </a>
      </div>
    </header>
  );
}
