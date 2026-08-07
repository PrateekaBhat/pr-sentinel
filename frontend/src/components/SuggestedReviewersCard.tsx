import type { SuggestedReviewer } from "../types";

interface Props {
  reviewers: SuggestedReviewer[];
}

export default function SuggestedReviewersCard({ reviewers }: Props) {
  if (!reviewers.length) return null;

  return (
    <ul className="flex flex-col gap-2">
      {reviewers.map((reviewer, i) => (
        <li
          key={`${reviewer.role}-${i}`}
          className="flex items-start gap-2.5 rounded-md border border-steel bg-raised px-3 py-2.5"
        >
          <span
            className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
              reviewer.required
                ? "border border-red-500/40 bg-red-500/10 text-red-400"
                : "border border-fog/40 bg-fog/10 text-fog"
            }`}
            aria-hidden="true"
          >
            {reviewer.required ? "Required" : "Recommended"}
          </span>
          <div className="flex flex-col gap-0.5">
            <span className="text-sm text-paper">{reviewer.role}</span>
            <span className="text-xs text-fog">{reviewer.reason}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
