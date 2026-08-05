from __future__ import annotations

import os
import re

# Disable Chroma's anonymized telemetry before importing the library.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

# Work around chromadb 0.5.x PostHog telemetry incompatibility with newer
# posthog.capture() signatures. If telemetry still initializes, this no-op
# wrapper prevents the broken capture call from logging an error.
try:
    import posthog

    def _noop_capture(*args, **kwargs):
        return None

    posthog.capture = _noop_capture
    posthog.disabled = True
except Exception:
    pass

import chromadb
from chromadb.config import Settings as ChromaSettings

from .. import ollama_client
from ..config import get_settings

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
MAX_BRANCH_NAME = 24

_client: chromadb.ClientAPI | None = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def _collection_name(owner: str, repo: str, branch: str = "main") -> str:
    safe_branch = re.sub(r"[^a-zA-Z0-9]+", "_", branch).strip("_")[:MAX_BRANCH_NAME] or "main"
    return f"repo_{owner}_{repo}_{safe_branch}".lower().replace("-", "_").replace(".", "_")[:63]


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += size - overlap
    return chunks


async def index_exists(owner: str, repo: str, branch: str) -> bool:
    client = _get_client()
    collection = client.get_or_create_collection(name=_collection_name(owner, repo, branch))
    return collection.count() > 0


async def get_or_build_index(owner: str, repo: str, branch: str, docs: list[dict]) -> tuple[int, int, bool]:
    """Indexes `docs` (list of {"path","content"}) into a per-repo, per-branch collection.
    Skips re-embedding if the branch-specific collection already exists.
    Returns (files_indexed, chunks_indexed, was_cached).
    """
    client = _get_client()
    collection = client.get_or_create_collection(name=_collection_name(owner, repo, branch))

    if collection.count() > 0:
        return len(docs), collection.count(), True

    ids, embeddings, documents, metadatas = [], [], [], []
    for doc in docs:
        for i, chunk in enumerate(chunk_text(doc["content"])):
            vector = await ollama_client.embed(chunk)
            ids.append(f"{doc['path']}::{i}")
            embeddings.append(vector)
            documents.append(chunk)
            metadatas.append({"path": doc["path"]})

    if ids:
        collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    return len(docs), len(ids), False


async def query(owner: str, repo: str, branch: str, query_text: str, top_k: int) -> list[dict]:
    client = _get_client()
    collection = client.get_or_create_collection(name=_collection_name(owner, repo, branch))
    if collection.count() == 0:
        return []

    query_vector = await ollama_client.embed(query_text)
    results = collection.query(query_embeddings=[query_vector], n_results=min(top_k, collection.count()))

    out = []
    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    for i in range(len(ids)):
        out.append(
            {
                "path": metadatas[i].get("path", "unknown"),
                "snippet": documents[i],
                "distance": distances[i],
            }
        )
    return out
