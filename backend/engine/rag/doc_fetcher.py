from __future__ import annotations

import re

from .. import github_client
from ..config import get_settings

DOC_PATH_RE = re.compile(
    r"(^|/)(readme|contributing|security|architecture|adr|design)[^/]*\.(md|mdx|rst|txt)$"
    r"|(^|/)docs?/.*\.(md|mdx|rst)$"
    r"|(^|/)(adr|design)/.*\.(md|mdx|rst)$",
    re.I,
)

# Generated / vendored directories that should never be indexed as repository
# documentation, even if they happen to contain a stray .md file.
_IGNORED_DIR_RE = re.compile(
    r"(^|/)(node_modules|dist|build|venv|\.venv|__pycache__|\.git|vendor|target)(/|$)",
    re.I,
)


def select_doc_paths(paths: list[str], limit: int) -> list[str]:
    candidates = [p for p in paths if not _IGNORED_DIR_RE.search(p)]
    matches = [p for p in candidates if DOC_PATH_RE.search(p)]
    # Prefer root-level and shallow files (README.md over docs/archive/old/notes.md)
    matches.sort(key=lambda p: (p.count("/"), len(p)))
    return matches[:limit]


async def fetch_repo_docs(owner: str, repo: str, token: str = "") -> tuple[list[dict], str, bool, str]:
    """Returns (docs, default_branch, truncated, skip_reason). docs is a list of
    {"path": str, "content": str}. skip_reason is '' on success."""
    settings = get_settings()

    try:
        default_branch = await github_client.fetch_default_branch(owner, repo, token)
        paths, truncated = await github_client.fetch_repo_tree(owner, repo, default_branch, token)
    except github_client.GitHubError as exc:
        return [], "", False, str(exc)

    doc_paths = select_doc_paths(paths, settings.rag_max_doc_files)
    if not doc_paths:
        return [], default_branch, truncated, "No README/docs files found in this repository."

    docs = []
    for path in doc_paths:
        content = await github_client.fetch_raw_file(
            owner, repo, default_branch, path, max_chars=settings.rag_max_doc_chars
        )
        if content.strip():
            docs.append({"path": path, "content": content})

    if not docs:
        return [], default_branch, truncated, "Doc files were found but couldn't be fetched."

    return docs, default_branch, truncated, ""
