interface Props {
  areas: string[];
  coveragePct?: number | null;
}

export default function TestAreasCard({ areas, coveragePct }: Props) {
  return (
    <div className="flex flex-col gap-3">
      {typeof coveragePct === "number" && (
        <p className="text-sm text-fog">
          Estimated modified-file test coverage:{" "}
          <span className="font-mono font-semibold text-paper">{coveragePct}%</span>
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {areas.map((area) => (
          <span
            key={area}
            className="flex items-center gap-1.5 rounded-md border border-steel bg-raised px-3 py-1.5 text-xs text-paper"
          >
            <span className="text-risk-low">✓</span>
            {area}
          </span>
        ))}
      </div>
    </div>
  );
}
