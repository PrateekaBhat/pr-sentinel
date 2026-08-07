import type { EngineeringMetrics } from "../types";

interface Props {
  metrics: EngineeringMetrics;
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col gap-1 rounded-md border border-steel bg-raised px-3 py-2.5">
      <span className="text-xs text-fog">{label}</span>
      <span className="font-mono text-sm font-semibold text-paper">{value}</span>
    </div>
  );
}

export default function EngineeringMetricsCard({ metrics: m }: Props) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      <Stat label="Public APIs / routes modified" value={m.public_apis_modified} />
      <Stat label="Config files changed" value={m.config_files_changed} />
      <Stat label="Workflow / CI files changed" value={m.workflow_files_changed} />
      <Stat label="Docs coverage of diff" value={`${m.documentation_coverage_pct}%`} />
      <Stat label="Test files touched" value={m.test_files_touched} />
      <Stat label="Dependency updates" value={m.dependency_updates} />
      <Stat label="Lines +/-" value={`+${m.lines_added} / -${m.lines_removed}`} />
      <Stat label="Files deleted" value={m.deleted_files} />
      <Stat label="Most impacted subsystem" value={m.most_impacted_subsystem} />
    </div>
  );
}
