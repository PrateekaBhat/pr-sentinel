import type { FileRisk, RiskLevel } from "../types";

const RISK_COLOR: Record<RiskLevel, string> = {
  LOW: "bg-risk-low",
  MEDIUM: "bg-risk-medium",
  HIGH: "bg-risk-high",
};

const RISK_WIDTH: Record<RiskLevel, string> = {
  LOW: "w-1/4",
  MEDIUM: "w-2/3",
  HIGH: "w-full",
};

export default function FileRiskList({ files }: { files: FileRisk[] }) {
  if (files.length === 0) {
    return <p className="text-sm text-fog">No individual files were flagged as high-risk.</p>;
  }

  return (
    <div className="flex flex-col divide-y divide-steel/60">
      {files.map((f) => (
        <div key={f.filename} className="py-3 first:pt-0 last:pb-0">
          <div className="flex items-center justify-between gap-3">
            <code className="truncate font-mono text-sm text-paper">{f.filename}</code>
            <span
              className={`shrink-0 rounded px-2 py-0.5 font-mono text-[11px] font-semibold ${
                f.risk === "HIGH"
                  ? "bg-risk-high/15 text-risk-high"
                  : f.risk === "MEDIUM"
                  ? "bg-risk-medium/15 text-risk-medium"
                  : "bg-risk-low/15 text-risk-low"
              }`}
            >
              {f.risk}
            </span>
          </div>
          <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-steel/60">
            <div className={`h-full rounded-full ${RISK_COLOR[f.risk]} ${RISK_WIDTH[f.risk]}`} />
          </div>
          <p className="mt-1.5 text-xs text-fog">{f.reason}</p>
        </div>
      ))}
    </div>
  );
}
