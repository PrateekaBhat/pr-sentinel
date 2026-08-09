import { useEffect, useState } from "react";

import { fetchGoldenTests } from "../api/client";
import type { GoldenTestsResponse } from "../types";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function GoldenTestsModal({ open, onClose }: Props) {
  const [data, setData] = useState<GoldenTestsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    fetchGoldenTests()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="max-h-[80vh] w-full max-w-lg overflow-auto rounded-xl border border-steel bg-panel p-6 shadow-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-display text-lg font-semibold text-paper">
            {data?.title ?? "PR Sentinel Policy Verification"}
          </h3>
          <button type="button" className="text-fog hover:text-paper" onClick={onClose}>
            ✕
          </button>
        </div>

        {loading && <p className="text-sm text-fog">Running golden tests…</p>}

        {data && (
          <>
            <p className="mb-4 font-mono text-sm text-paper">
              {data.passed} / {data.total} PASSED
            </p>
            <ul className="flex flex-col gap-2">
              {data.tests.map((test) => (
                <li key={test.id} className="rounded-lg border border-steel">
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
                    onClick={() => setExpanded(expanded === test.id ? null : test.id)}
                  >
                    <span className={test.passed ? "text-risk-low" : "text-risk-high"}>
                      {test.passed ? "✓" : "✗"}
                    </span>
                    <span className="text-paper">{test.name}</span>
                  </button>
                  {expanded === test.id && (
                    <div className="border-t border-steel px-3 py-2 font-mono text-[11px] text-fog">
                      Expected → {test.expected} · Actual → {test.actual}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
