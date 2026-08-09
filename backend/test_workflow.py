from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the PR Sentinel CLI flow locally and validate its output.")
    parser.add_argument("--repo", required=True, help="GitHub repository in owner/repo format.")
    parser.add_argument("--pr", required=True, type=int, help="Pull request number.")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""), help="GitHub token for API requests.")
    parser.add_argument("--output-dir", default="reports", help="Directory to write report.json and report.md.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "cli.py",
        "analyze",
        "--repo",
        args.repo,
        "--pr",
        str(args.pr),
        "--output",
        str(output_dir / "report.json"),
        "--comment",
        str(output_dir / "report.md"),
    ]
    if args.token:
        command.extend(["--token", args.token])

    print("Running PR Sentinel CLI flow...")
    result = subprocess.run(command, cwd=Path(__file__).parent, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    report_path = output_dir / "report.json"

    # Exit-code handling mirrors cli.py exactly: 0 = ALLOW/NEEDS_REVIEW, 1 = BLOCK,
    # 2+ = analysis/runtime failure. The presence of a report.json file (which may be
    # stale from a previous run) must never override what the subprocess actually reported.
    if result.returncode not in (0, 1):
        print(f"PR Sentinel CLI failed unexpectedly (exit code {result.returncode}).")
        return result.returncode

    if not report_path.exists():
        print(f"ERROR: CLI reported success (exit code {result.returncode}) but expected report file not found: {report_path}")
        return 2

    with report_path.open("r", encoding="utf-8") as handle:
        report = json.load(handle)

    decision = report.get("report", {}).get("decision")
    print(f"Report decision: {decision}")
    print(f"Report location: {report_path}")
    print(f"Markdown summary: {output_dir / 'report.md'}")

    if result.returncode == 1:
        print("PR Sentinel returned BLOCK. The full flow is working and would fail a CI job.")
    else:
        print("PR Sentinel returned ALLOW/NEEDS_REVIEW. The full flow is working and would pass a CI job.")

    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
