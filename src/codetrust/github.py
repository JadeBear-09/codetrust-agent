from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import PurePosixPath

PR_REF = re.compile(r"^(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(?P<number>[1-9]\d*)$")
PR_URL = re.compile(
    r"^https://github\.com/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/pull/(?P<number>[1-9]\d*)/?$"
)
POLICY_PATHS = (
    ".codetrust/policy.md",
    "CODETRUST.md",
    ".github/CODETRUST.md",
    "docs/CODETRUST.md",
    "PRODUCT.md",
    "docs/PRODUCT.md",
)
MAX_POLICY_BYTES = 100_000


@dataclass(frozen=True)
class PullRequestComment:
    author: str
    association: str
    body: str
    url: str
    created_at: str


@dataclass(frozen=True)
class PullRequestChange:
    ticket: str
    diff: str
    repo: str
    number: int
    url: str
    base_sha: str
    head_sha: str
    state: str = "UNKNOWN"
    closed_at: str | None = None
    merged_at: str | None = None
    author: str = ""
    comments: tuple[PullRequestComment, ...] = ()


@dataclass(frozen=True)
class RepositoryPolicy:
    path: str
    content: str
    sha256: str


def load_pull_request(reference: str) -> PullRequestChange:
    reference = normalize_pr_reference(reference)
    match = PR_REF.fullmatch(reference)
    if not match:
        raise ValueError("PR must use OWNER/REPO#NUMBER format")
    repo = match.group("repo")
    number = int(match.group("number"))
    fields = "title,body,url,baseRefOid,headRefOid,state,closedAt,mergedAt,author,comments"
    metadata = _run_gh(["pr", "view", str(number), "--repo", repo, "--json", fields])
    diff = _run_gh(["pr", "diff", str(number), "--repo", repo])
    parsed = json.loads(metadata)
    body = str(parsed.get("body") or "No PR description supplied.")
    ticket = f"# {parsed['title']}\n\n{body}"
    author = parsed.get("author") or {}
    comments = tuple(
        PullRequestComment(
            author=str((item.get("author") or {}).get("login") or "unknown"),
            association=str(item.get("authorAssociation") or "NONE").upper(),
            body=str(item.get("body") or ""),
            url=str(item.get("url") or ""),
            created_at=str(item.get("createdAt") or ""),
        )
        for item in parsed.get("comments") or []
    )
    return PullRequestChange(
        ticket=ticket,
        diff=diff,
        repo=repo,
        number=number,
        url=str(parsed["url"]),
        base_sha=str(parsed["baseRefOid"]),
        head_sha=str(parsed["headRefOid"]),
        state=str(parsed.get("state") or "UNKNOWN").upper(),
        closed_at=parsed.get("closedAt"),
        merged_at=parsed.get("mergedAt"),
        author=str(author.get("login") or ""),
        comments=comments,
    )


def load_repository_policy(repo: str, revision: str) -> RepositoryPolicy | None:
    """Load first canonical policy from trusted base revision without checking out code."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not re.fullmatch(
        r"[0-9a-fA-F]{7,64}", revision
    ):
        raise ValueError("Repository or base revision is invalid")
    for path in repository_policy_paths():
        try:
            content = _run_gh(
                [
                    "api",
                    "--method",
                    "GET",
                    f"repos/{repo}/contents/{path}",
                    "-f",
                    f"ref={revision}",
                    "-H",
                    "Accept: application/vnd.github.raw+json",
                ]
            )
        except RuntimeError as exc:
            if "HTTP 404" in str(exc) or "Not Found" in str(exc):
                continue
            raise
        encoded = content.encode()
        if len(encoded) > MAX_POLICY_BYTES:
            raise RuntimeError(f"Repository policy `{path}` exceeds {MAX_POLICY_BYTES} bytes")
        return RepositoryPolicy(
            path=path,
            content=content,
            sha256=hashlib.sha256(encoded).hexdigest(),
        )
    return None


def repository_policy_paths() -> tuple[str, ...]:
    configured = os.getenv("CODETRUST_POLICY_PATHS", "")
    candidates = tuple(item.strip() for item in configured.split(",") if item.strip())
    paths = candidates or POLICY_PATHS
    for path in paths:
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError(f"Unsafe repository policy path: {path}")
    return paths


def normalize_pr_reference(value: str) -> str:
    cleaned = value.strip()
    if PR_REF.fullmatch(cleaned):
        return cleaned
    url_match = PR_URL.fullmatch(cleaned)
    if url_match:
        return f"{url_match.group('repo')}#{url_match.group('number')}"
    raise ValueError("PR must use OWNER/REPO#NUMBER or a GitHub pull-request URL")


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
