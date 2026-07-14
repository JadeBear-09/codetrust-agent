from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

PR_REF = re.compile(r"^(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(?P<number>[1-9]\d*)$")


@dataclass(frozen=True)
class PullRequestChange:
    ticket: str
    diff: str
    repo: str
    number: int
    url: str
    base_sha: str
    head_sha: str


def load_pull_request(reference: str) -> PullRequestChange:
    match = PR_REF.fullmatch(reference.strip())
    if not match:
        raise ValueError("PR must use OWNER/REPO#NUMBER format")
    repo = match.group("repo")
    number = int(match.group("number"))
    fields = "title,body,url,baseRefOid,headRefOid"
    metadata = _run_gh(["pr", "view", str(number), "--repo", repo, "--json", fields])
    diff = _run_gh(["pr", "diff", str(number), "--repo", repo])
    parsed = json.loads(metadata)
    body = str(parsed.get("body") or "No PR description supplied.")
    ticket = f"# {parsed['title']}\n\n{body}"
    return PullRequestChange(
        ticket=ticket,
        diff=diff,
        repo=repo,
        number=number,
        url=str(parsed["url"]),
        base_sha=str(parsed["baseRefOid"]),
        head_sha=str(parsed["headRefOid"]),
    )


def _run_gh(arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            ["gh", *arguments],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("GitHub CLI `gh` is required for PR ingestion") from exc
    if result.returncode:
        message = result.stderr.strip() or "GitHub CLI request failed"
        raise RuntimeError(message)
    return result.stdout
