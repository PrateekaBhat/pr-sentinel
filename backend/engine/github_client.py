from __future__ import annotations

import re

import httpx

from .models import ChangedFile, PullRequestData

GITHUB_API = "https://api.github.com"

PR_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)


class GitHubError(Exception):
    """Raised when a PR URL can't be parsed or GitHub returns an error."""


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    match = PR_URL_RE.match(pr_url.strip())
    if not match:
        raise GitHubError(
            "That doesn't look like a GitHub pull request URL. "
            "Expected something like https://github.com/owner/repo/pull/123"
        )
    return match.group("owner"), match.group("repo"), int(match.group("number"))


async def fetch_pull_request(owner: str, repo: str, number: int, token: str = "") -> PullRequestData:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(base_url=GITHUB_API, headers=headers, timeout=20.0) as client:
        pr_resp = await client.get(f"/repos/{owner}/{repo}/pulls/{number}")
        _raise_for_github_status(pr_resp)
        pr_json = pr_resp.json()

        files_resp = await client.get(
            f"/repos/{owner}/{repo}/pulls/{number}/files", params={"per_page": 100}
        )
        _raise_for_github_status(files_resp)
        files_json = files_resp.json()

        commits_resp = await client.get(
            f"/repos/{owner}/{repo}/pulls/{number}/commits", params={"per_page": 100}
        )
        _raise_for_github_status(commits_resp)
        commits_json = commits_resp.json()

    files = [
        ChangedFile(
            filename=f["filename"],
            status=f.get("status", "modified"),
            additions=f.get("additions", 0),
            deletions=f.get("deletions", 0),
            changes=f.get("changes", 0),
            patch=f.get("patch"),
        )
        for f in files_json
    ]

    repository_json = pr_json.get("base", {}).get("repo", {})
    return PullRequestData(
        owner=owner,
        repo=repo,
        number=number,
        title=pr_json.get("title", ""),
        body=pr_json.get("body") or "",
        author=(pr_json.get("user") or {}).get("login", "unknown"),
        url=pr_json.get("html_url", f"https://github.com/{owner}/{repo}/pull/{number}"),
        created_at=pr_json.get("created_at"),
        mergeable_state=pr_json.get("mergeable_state"),
        mergeable=pr_json.get("mergeable"),
        state=pr_json.get("state", "open"),
        additions=pr_json.get("additions", 0),
        deletions=pr_json.get("deletions", 0),
        changed_files_count=pr_json.get("changed_files", len(files)),
        labels=[label.get("name", "") for label in pr_json.get("labels", [])],
        commit_messages=[c.get("commit", {}).get("message", "") for c in commits_json],
        files=files,
        repository={
            "owner": repository_json.get("owner", {}).get("login", owner),
            "name": repository_json.get("name", repo),
            "full_name": repository_json.get("full_name", f"{owner}/{repo}"),
            "description": repository_json.get("description"),
            "primary_language": repository_json.get("language"),
            "stars": repository_json.get("stargazers_count", 0),
            "topics": repository_json.get("topics", []),
            "default_branch": repository_json.get("default_branch"),
            "size_kb": repository_json.get("size", 0),
        },
        head_branch=(pr_json.get("head") or {}).get("ref"),
        base_branch=(pr_json.get("base") or {}).get("ref"),
    )


async def fetch_default_branch(owner: str, repo: str, token: str = "") -> str:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(base_url=GITHUB_API, headers=headers, timeout=15.0) as client:
        resp = await client.get(f"/repos/{owner}/{repo}")
        _raise_for_github_status(resp)
        return resp.json().get("default_branch", "main")


async def fetch_repo_tree(owner: str, repo: str, branch: str, token: str = "") -> tuple[list[str], bool]:
    """Returns (list of file paths, truncated). Raises GitHubError on failure."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(base_url=GITHUB_API, headers=headers, timeout=20.0) as client:
        resp = await client.get(f"/repos/{owner}/{repo}/git/trees/{branch}", params={"recursive": "1"})
        _raise_for_github_status(resp)
        body = resp.json()

    paths = [item["path"] for item in body.get("tree", []) if item.get("type") == "blob"]
    return paths, bool(body.get("truncated", False))


async def fetch_raw_file(owner: str, repo: str, branch: str, path: str, max_chars: int = 4000) -> str:
    """Fetches a file's raw content from raw.githubusercontent.com. Returns '' on failure
    rather than raising, since this is used for best-effort doc indexing."""
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return ""
        return resp.text[:max_chars]
    except httpx.HTTPError:
        return ""


def _raise_for_github_status(resp: httpx.Response) -> None:
    if resp.status_code == 404:
        raise GitHubError("Pull request not found. Check the URL and that the repo is public.")
    if resp.status_code == 403:
        raise GitHubError(
            "GitHub rate limit hit. Add a GITHUB_TOKEN to backend/.env to raise the limit."
        )
    if resp.status_code >= 400:
        raise GitHubError(f"GitHub API error ({resp.status_code}): {resp.text[:200]}")
