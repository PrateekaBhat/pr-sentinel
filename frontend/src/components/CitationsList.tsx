import type { RAGChunk, RAGContext } from "../types";

function CitationRow({ chunk }: { chunk: RAGChunk }) {
  return (
    <div className="rounded-md border border-steel bg-raised px-3 py-2.5">
      <div className="mb-1 flex items-center justify-between gap-2">
        <code className="truncate font-mono text-xs text-risk-medium">{chunk.path}</code>
        <span className="shrink-0 font-mono text-[10px] text-fog">
          {Math.round(chunk.score * 100)}% match
        </span>
      </div>
      <p className="text-xs leading-relaxed text-fog">{chunk.snippet}</p>
    </div>
  );
}

export default function CitationsList({ rag }: { rag: RAGContext }) {
  if (!rag.scanned) {
    return (
      <p className="text-sm text-fog">
        Repository documentation wasn't indexed{rag.skip_reason ? ` — ${rag.skip_reason}` : "."}
      </p>
    );
  }

  if (rag.retrieved.length === 0) {
    return (
      <p className="text-sm text-fog">
        Indexed {rag.indexed_files} doc file(s) from this repo, but nothing closely matched
        this PR's files.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-fog">
        Retrieved from {rag.indexed_files} indexed doc file(s) ({rag.chunks_indexed} chunks) on{" "}
        <span className="font-mono text-paper">{rag.default_branch}</span>
      </p>
      {rag.retrieved.map((chunk, i) => (
        <CitationRow key={i} chunk={chunk} />
      ))}
    </div>
  );
}
