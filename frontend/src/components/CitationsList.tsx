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
        Repository documentation wasn't indexed{rag.skip_reason ? ` — ${rag.skip_reason}` : ""}.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-fog">
        Indexed {rag.indexed_files} doc file(s) into {rag.chunks_indexed} chunk(s) from{" "}
        <span className="font-mono text-paper">{rag.default_branch}</span>
        {rag.cache_hit ? " (cache hit)" : " (freshly indexed)"}.
      </p>

      {rag.indexed_doc_paths.length > 0 && (
        <div>
          <p className="mb-1.5 font-mono text-[11px] uppercase tracking-wider text-fog">
            Retrieved documents
          </p>
          <div className="flex flex-wrap gap-1.5">
            {rag.indexed_doc_paths.map((p) => (
              <code
                key={p}
                className="rounded border border-steel bg-raised px-2 py-1 font-mono text-[11px] text-paper"
              >
                {p}
              </code>
            ))}
          </div>
        </div>
      )}

      {rag.retrieved.length > 0 ? (
        <div>
          <p className="mb-1.5 font-mono text-[11px] uppercase tracking-wider text-fog">
            Top context snippets used in this analysis
          </p>
          <div className="flex flex-col gap-2">
            {rag.retrieved.map((chunk, i) => (
              <CitationRow key={i} chunk={chunk} />
            ))}
          </div>
        </div>
      ) : (
        <p className="text-sm text-fog">
          Nothing closely matched this PR's files, so no snippet was used as supporting context.
        </p>
      )}
    </div>
  );
}
