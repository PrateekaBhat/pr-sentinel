from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from engine.service import analyze_pr, render_comment


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PR Sentinel CLI — analyze GitHub pull requests for deployment risk."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze a GitHub pull request.")
    analyze.add_argument("--repo", required=True, help="GitHub repository in owner/repo format.")
    analyze.add_argument("--pr", required=True, type=int, help="Pull request number.")
    analyze.add_argument(
        "--output",
        default="-",
        help="Path to write JSON report, or '-' for stdout. Defaults to stdout.",
    )
    analyze.add_argument(
        "--comment",
        help="Optional path to write PR summary markdown for GitHub comments.",
    )
    analyze.add_argument(
        "--token",
        help="GitHub token to use for API requests. Falls back to GITHUB_TOKEN environment variable.",
    )
    return parser.parse_args()


async def _run_analyze(args: argparse.Namespace) -> int:
    token = args.token or os.environ.get("GITHUB_TOKEN", "")
    if "/" not in args.repo:
        raise ValueError("--repo must be in owner/repo format.")
    owner, repo = args.repo.split("/", 1)
    response = await analyze_pr(owner, repo, args.pr, token=token)
    report_json = json.dumps(response.model_dump(mode="json"), indent=2)

    if args.output == "-":
        print(report_json)
    else:
        Path(args.output).write_text(report_json, encoding="utf-8")

    if args.comment:
        comment_text = render_comment(response)
        Path(args.comment).write_text(comment_text, encoding="utf-8")

    return 1 if response.report.decision == "BLOCK" else 0


def main() -> int:
    args = _parse_args()
    if args.command == "analyze":
        return asyncio.run(_run_analyze(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
