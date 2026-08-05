from __future__ import annotations

import logging

from .. import github_client
from ..config import get_settings
from ..models import PullRequestData, RAGChunk, RAGContext
from ..ollama_client import OllamaError
from . import doc_fetcher, store

logger = logging.getLogger("pr_sentinel.rag")


def _build_query(pr: PullRequestData) -> str:
    top_files = ", ".join(f.filename for f in pr.files[:10])
    return f"{pr.title}. Labels: {', '.join(pr.labels)}. Files changed: {top_files}"


async def get_rag_context(pr: PullRequestData, token: str = "") -> RAGContext:
    settings = get_settings()
    if not settings.rag_enabled:
        return RAGContext(scanned=False, skip_reason="RAG disabled via config.")

    default_branch = await github_client.fetch_default_branch(pr.owner, pr.repo, token)

    if await store.index_exists(pr.owner, pr.repo, default_branch):
        try:
            raw_hits = await store.query(pr.owner, pr.repo, default_branch, _build_query(pr), settings.rag_top_k)
        except OllamaError as exc:
            logger.warning("RAG embedding unavailable, skipping repo context: %s", exc)
            return RAGContext(
                scanned=False,
                default_branch=default_branch,
                skip_reason=f"Embedding model unavailable: {exc}",
            )

        retrieved = [
            RAGChunk(path=hit["path"], snippet=hit["snippet"][:500], score=1 - hit["distance"])
            for hit in raw_hits
        ]

        return RAGContext(
            scanned=True,
            default_branch=default_branch,
            indexed_files=0,
            chunks_indexed=len(retrieved),
            retrieved=retrieved,
        )

    docs, default_branch, truncated, skip_reason = await doc_fetcher.fetch_repo_docs(
        pr.owner, pr.repo, token
    )
    if skip_reason:
        return RAGContext(scanned=False, default_branch=default_branch or None, skip_reason=skip_reason)

    try:
        indexed_files, chunks_indexed, _cached = await store.get_or_build_index(
            pr.owner, pr.repo, default_branch, docs
        )
        raw_hits = await store.query(pr.owner, pr.repo, default_branch, _build_query(pr), settings.rag_top_k)
    except OllamaError as exc:
        logger.warning("RAG embedding unavailable, skipping repo context: %s", exc)
        return RAGContext(
            scanned=False,
            default_branch=default_branch,
            skip_reason=f"Embedding model unavailable: {exc}",
        )

    retrieved = [
        RAGChunk(path=hit["path"], snippet=hit["snippet"][:500], score=1 - hit["distance"])
        for hit in raw_hits
    ]

    return RAGContext(
        scanned=True,
        default_branch=default_branch,
        indexed_files=indexed_files,
        chunks_indexed=chunks_indexed,
        retrieved=retrieved,
    )
