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

    return PullRequestData(
        owner=owner,
        repo=repo,
        number=number,
        title=pr_json.get("title", ""),
        body=pr_json.get("body") or "",
        author=(pr_json.get("user") or {}).get("login", "unknown"),
        url=pr_json.get("html_url", f"https://github.com/{owner}/{repo}/pull/{number}"),
        additions=pr_json.get("additions", 0),
        deletions=pr_json.get("deletions", 0),
        changed_files_count=pr_json.get("changed_files", len(files)),
        labels=[label.get("name", "") for label in pr_json.get("labels", [])],
        commit_messages=[c.get("commit", {}).get("message", "") for c in commits_json],
        files=files,
    )


def _raise_for_github_status(resp: httpx.Response) -> None:
    if resp.status_code == 404:
        raise GitHubError("Pull request not found. Check the URL and that the repo is public.")
    if resp.status_code == 403:
        raise GitHubError(
            "GitHub rate limit hit. Add a GITHUB_TOKEN to backend/.env to raise the limit."
        )
    if resp.status_code >= 400:
        raise GitHubError(f"GitHub API error ({resp.status_code}): {resp.text[:200]}")
