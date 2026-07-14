from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from codetrust.agent import verify_change
from codetrust.github import load_pull_request
from codetrust.report import write_reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codetrust",
        description="Verify a software change and emit an evidence pack.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify", help="Analyze ticket and software change")
    verify.add_argument("--ticket", type=Path, help="Ticket or acceptance criteria")
    source = verify.add_mutually_exclusive_group(required=True)
    source.add_argument("--diff", type=Path, help="Unified diff file")
    source.add_argument("--git-range", help="Local git range, for example main...HEAD")
    source.add_argument("--github-pr", help="GitHub PR as OWNER/REPO#NUMBER")
    verify.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository for --git-range")
    verify.add_argument("--output-dir", type=Path, default=Path("reports"))
    verify.add_argument("--offline", action="store_true", help="Skip model synthesis")

    serve = subparsers.add_parser("serve", help="Run local verification dashboard")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        from codetrust.web import run_server

        run_server(args.host, args.port)
        return 0
    if args.command != "verify":
        return 2

    source = {"type": "diff"}
    if args.github_pr:
        change = load_pull_request(args.github_pr)
        ticket = args.ticket.read_text() if args.ticket else change.ticket
        diff = change.diff
        source = {
            "type": "github-pr",
            "reference": args.github_pr,
            "url": change.url,
            "base_sha": change.base_sha,
            "head_sha": change.head_sha,
        }
    else:
        if not args.ticket:
            raise SystemExit("--ticket is required with --diff or --git-range")
        ticket = args.ticket.read_text()
        diff = args.diff.read_text() if args.diff else _git_diff(args.repo, args.git_range)
        source = {"type": "diff" if args.diff else "git-range"}
    report = verify_change(ticket, diff, offline=args.offline, source=source)
    paths = write_reports(report, args.output_dir)
    print(
        f"{report.verdict.value} · risk {report.risk_score}/100 · {len(report.findings)} finding(s)"
    )
    for name, path in paths.items():
        print(f"{name}: {path.resolve()}")
    return 1 if report.verdict.value == "BLOCK" else 0


def _git_diff(repo: Path, git_range: str) -> str:
    result = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--unified=3", git_range],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    return result.stdout


if __name__ == "__main__":
    raise SystemExit(main())
