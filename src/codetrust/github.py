from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import PurePosixPath

PR_REF = re.compile(r"^(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(?P<number>[1-9]\d*)$")
PR_URL = re.compile(
    r"^https://github\.com/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/pull/(?P<number>[1-9]\d*)/?$"
)
MAX_REPOSITORY_DOCUMENTS = 12
MAX_REPOSITORY_DOCUMENT_BYTES = 100_000
MAX_REPOSITORY_CONTEXT_BYTES = 300_000
MAX_REPOSITORY_STRUCTURE_PATHS = 400
MAX_REPOSITORY_SOURCE_FILES = 12
MAX_REPOSITORY_SOURCE_FILE_BYTES = 80_000
MAX_REPOSITORY_SOURCE_CONTEXT_BYTES = 240_000
GENERAL_DOCUMENT_STEMS = (
    "readme",
    "contributing",
    "architecture",
    "design",
    "overview",
    "about",
    "purpose",
    "vision",
    "roadmap",
    "development",
    "hacking",
    "security",
)
GENERAL_DOCUMENT_SUFFIXES = {"", ".md", ".rst", ".txt", ".adoc"}
DOCUMENTATION_DIRECTORIES = {".github", "doc", "docs", "documentation"}
EXCLUDED_CONTEXT_DIRECTORIES = {
    "borrowed",
    "build",
    "dependencies",
    "deps",
    "dist",
    "external",
    "externals",
    "node_modules",
    "third-party",
    "third_party",
    "vendor",
    "vendors",
}
BINARY_CONTEXT_SUFFIXES = {
    ".7z",
    ".a",
    ".avi",
    ".bin",
    ".bmp",
    ".class",
    ".dll",
    ".dylib",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".mov",
    ".mp3",
    ".mp4",
    ".o",
    ".pdf",
    ".png",
    ".so",
    ".tar",
    ".ttf",
    ".wav",
    ".webp",
    ".woff",
    ".woff2",
    ".zip",
}
REPOSITORY_MANIFEST_NAMES = {
    "build.gradle",
    "build.gradle.kts",
    "cargo.toml",
    "composer.json",
    "gemfile",
    "go.mod",
    "mix.exs",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
}


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
    author: str = ""


@dataclass(frozen=True)
class RepositoryDocument:
    path: str
    content: str
    sha256: str


@dataclass(frozen=True)
class RepositoryMetadata:
    description: str = ""
    homepage: str = ""
    language: str = ""
    topics: tuple[str, ...] = ()
    created_at: str = ""
    default_branch: str = ""


@dataclass(frozen=True)
class RepositoryHistoryEntry:
    sha: str
    title: str
    date: str


@dataclass(frozen=True)
class RepositoryContext:
    documents: tuple[RepositoryDocument, ...]
    structure: tuple[str, ...]
    sha256: str
    tree_truncated: bool = False
    source_files: tuple[RepositoryDocument, ...] = ()
    metadata: RepositoryMetadata | None = None
    history: tuple[RepositoryHistoryEntry, ...] = ()


def load_pull_request(reference: str) -> PullRequestChange:
    reference = normalize_pr_reference(reference)
    match = PR_REF.fullmatch(reference)
    if not match:
        raise ValueError("PR must use OWNER/REPO#NUMBER format")
    repo = match.group("repo")
    number = int(match.group("number"))
    fields = "title,body,url,baseRefOid,headRefOid,state,author"
    metadata = _run_gh(["pr", "view", str(number), "--repo", repo, "--json", fields])
    diff = _run_gh(["pr", "diff", str(number), "--repo", repo])
    parsed = json.loads(metadata)
    body = str(parsed.get("body") or "No PR description supplied.")
    ticket = f"# {parsed['title']}\n\n{body}"
    author = parsed.get("author") or {}
    return PullRequestChange(
        ticket=ticket,
        diff=diff,
        repo=repo,
        number=number,
        url=str(parsed["url"]),
        base_sha=str(parsed["baseRefOid"]),
        head_sha=str(parsed["headRefOid"]),
        state=str(parsed.get("state") or "UNKNOWN").upper(),
        author=str(author.get("login") or ""),
    )


def load_repository_context(
    repo: str,
    revision: str,
    changed_paths: tuple[str, ...] = (),
) -> RepositoryContext:
    """Read bounded general documentation and structure from exact base revision."""
    _validate_repository_revision(repo, revision)
    raw_tree = _run_gh(
        [
            "api",
            "--method",
            "GET",
            f"repos/{repo}/git/trees/{revision}?recursive=1",
        ]
    )
    try:
        tree = json.loads(raw_tree)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub returned invalid repository tree data") from exc
    entries = tree.get("tree")
    if not isinstance(entries, list):
        raise RuntimeError("GitHub repository tree response is missing entries")

    blobs: list[tuple[str, int]] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "blob":
            continue
        path = str(entry.get("path") or "")
        if not _safe_repository_path(path):
            continue
        try:
            size = int(entry.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        blobs.append((path, size))

    candidates = sorted(
        (
            (_general_document_priority(path), path, size)
            for path, size in blobs
            if _general_document_priority(path) is not None
        ),
        key=lambda item: (item[0], item[1].lower()),
    )
    documents: list[RepositoryDocument] = []
    total_bytes = 0
    stem_counts: dict[str, int] = {}
    for _priority, path, declared_size in candidates:
        if len(documents) >= MAX_REPOSITORY_DOCUMENTS:
            break
        stem = PurePosixPath(path).stem.lower()
        if stem_counts.get(stem, 0) >= 4:
            continue
        if declared_size > MAX_REPOSITORY_DOCUMENT_BYTES:
            continue
        try:
            content = _load_repository_file(repo, revision, path)
        except RuntimeError:
            continue
        encoded = content.encode()
        if len(encoded) > MAX_REPOSITORY_DOCUMENT_BYTES:
            continue
        if total_bytes + len(encoded) > MAX_REPOSITORY_CONTEXT_BYTES:
            continue
        documents.append(
            RepositoryDocument(
                path=path,
                content=content,
                sha256=hashlib.sha256(encoded).hexdigest(),
            )
        )
        total_bytes += len(encoded)
        stem_counts[stem] = stem_counts.get(stem, 0) + 1

    blob_sizes = {path: size for path, size in blobs}
    source_files: list[RepositoryDocument] = []
    source_bytes = 0
    document_paths = {item.path for item in documents}
    for path in _source_context_paths(tuple(path for path, _size in blobs), changed_paths):
        if len(source_files) >= MAX_REPOSITORY_SOURCE_FILES:
            break
        declared_size = blob_sizes.get(path)
        if declared_size is None or path in document_paths:
            continue
        if PurePosixPath(path).suffix.lower() in BINARY_CONTEXT_SUFFIXES:
            continue
        if declared_size > MAX_REPOSITORY_SOURCE_FILE_BYTES:
            continue
        try:
            content = _load_repository_file(repo, revision, path)
        except RuntimeError:
            continue
        encoded = content.encode()
        if b"\x00" in encoded or len(encoded) > MAX_REPOSITORY_SOURCE_FILE_BYTES:
            continue
        if source_bytes + len(encoded) > MAX_REPOSITORY_SOURCE_CONTEXT_BYTES:
            continue
        source_files.append(
            RepositoryDocument(
                path=path,
                content=content,
                sha256=hashlib.sha256(encoded).hexdigest(),
            )
        )
        source_bytes += len(encoded)

    structure = _select_structure_paths(
        tuple(path for path, _size in blobs),
        changed_paths,
    )
    metadata = _load_repository_metadata(repo)
    history = _load_repository_history(repo, revision)
    digest_payload = json.dumps(
        {
            "documents": [(item.path, item.sha256) for item in documents],
            "source_files": [(item.path, item.sha256) for item in source_files],
            "structure": structure,
            "tree_truncated": bool(tree.get("truncated")),
            "metadata": metadata.__dict__ if metadata else None,
            "history": [item.__dict__ for item in history],
        },
        sort_keys=True,
    )
    return RepositoryContext(
        documents=tuple(documents),
        structure=structure,
        sha256=hashlib.sha256(digest_payload.encode()).hexdigest(),
        tree_truncated=bool(tree.get("truncated")),
        source_files=tuple(source_files),
        metadata=metadata,
        history=history,
    )


def _validate_repository_revision(repo: str, revision: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not re.fullmatch(
        r"[0-9a-fA-F]{7,64}", revision
    ):
        raise ValueError("Repository or base revision is invalid")


def _safe_repository_path(path: str) -> bool:
    parsed = PurePosixPath(path)
    return bool(path) and not parsed.is_absolute() and ".." not in parsed.parts


def _general_document_priority(path: str) -> int | None:
    parsed = PurePosixPath(path)
    lowered_parts = {part.lower() for part in parsed.parts[:-1]}
    if lowered_parts & EXCLUDED_CONTEXT_DIRECTORIES:
        return None
    suffix = parsed.suffix.lower()
    if suffix not in GENERAL_DOCUMENT_SUFFIXES:
        return None
    stem = parsed.stem.lower() if suffix else parsed.name.lower()
    matched = next(
        (
            index
            for index, candidate in enumerate(GENERAL_DOCUMENT_STEMS)
            if stem == candidate
            or stem.startswith(f"{candidate}.")
            or stem.startswith(f"{candidate}-")
            or stem.startswith(f"{candidate}_")
        ),
        None,
    )
    if matched is None:
        return None
    if len(parsed.parts) == 1:
        return matched
    if parsed.parts[0].lower() in DOCUMENTATION_DIRECTORIES:
        return 20 + matched + min(len(parsed.parts) - 1, 4)
    return 100 + (matched * 5) + min(len(parsed.parts) - 1, 9)


def _load_repository_file(repo: str, revision: str, path: str) -> str:
    return _run_gh(
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


def _load_repository_metadata(repo: str) -> RepositoryMetadata | None:
    try:
        parsed = json.loads(_run_gh(["api", "--method", "GET", f"repos/{repo}"]))
    except (RuntimeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    raw_topics = parsed.get("topics") or []
    topics = tuple(str(item) for item in raw_topics[:20]) if isinstance(raw_topics, list) else ()
    return RepositoryMetadata(
        description=str(parsed.get("description") or "")[:500],
        homepage=str(parsed.get("homepage") or "")[:500],
        language=str(parsed.get("language") or "")[:100],
        topics=topics,
        created_at=str(parsed.get("created_at") or "")[:100],
        default_branch=str(parsed.get("default_branch") or "")[:200],
    )


def _load_repository_history(
    repo: str,
    revision: str,
) -> tuple[RepositoryHistoryEntry, ...]:
    try:
        parsed = json.loads(
            _run_gh(
                [
                    "api",
                    "--method",
                    "GET",
                    f"repos/{repo}/commits",
                    "-f",
                    f"sha={revision}",
                    "-f",
                    "per_page=20",
                ]
            )
        )
    except (RuntimeError, json.JSONDecodeError):
        return ()
    if not isinstance(parsed, list):
        return ()
    entries: list[RepositoryHistoryEntry] = []
    for item in parsed[:20]:
        if not isinstance(item, dict):
            continue
        commit = item.get("commit") or {}
        if not isinstance(commit, dict):
            continue
        author = commit.get("author") or {}
        message = str(commit.get("message") or "").splitlines()[0]
        entries.append(
            RepositoryHistoryEntry(
                sha=str(item.get("sha") or "")[:40],
                title=message[:300],
                date=str(author.get("date") or "")[:100] if isinstance(author, dict) else "",
            )
        )
    return tuple(entries)


def _select_structure_paths(
    paths: tuple[str, ...],
    changed_paths: tuple[str, ...],
) -> tuple[str, ...]:
    known = set(paths)
    selected: list[str] = []

    def add(path: str) -> None:
        if path in known and path not in selected:
            selected.append(path)

    for path in changed_paths:
        add(path)
    for changed in changed_paths:
        parent = str(PurePosixPath(changed).parent)
        siblings = sorted(path for path in paths if str(PurePosixPath(path).parent) == parent)
        for path in siblings[:30]:
            add(path)

    roots: dict[str, int] = {}
    for path in sorted(paths):
        root = PurePosixPath(path).parts[0]
        count = roots.get(root, 0)
        if count < 8:
            add(path)
            roots[root] = count + 1
        if len(selected) >= MAX_REPOSITORY_STRUCTURE_PATHS:
            break
    return tuple(selected[:MAX_REPOSITORY_STRUCTURE_PATHS])


def _source_context_paths(
    paths: tuple[str, ...],
    changed_paths: tuple[str, ...],
) -> tuple[str, ...]:
    """Choose changed base files, related tests/code, and shallow manifests."""
    known = set(paths)
    selected: list[str] = []

    def eligible(path: str) -> bool:
        parsed = PurePosixPath(path)
        directories = {part.lower() for part in parsed.parts[:-1]}
        return (
            path in known
            and not directories & EXCLUDED_CONTEXT_DIRECTORIES
            and parsed.suffix.lower() not in BINARY_CONTEXT_SUFFIXES
        )

    def add(path: str) -> None:
        if eligible(path) and path not in selected:
            selected.append(path)

    for path in changed_paths:
        add(path)

    for changed in changed_paths:
        changed_stem = _context_stem(changed)
        if not changed_stem:
            continue
        related = sorted(
            path
            for path in paths
            if path != changed and eligible(path) and _context_stem(path) == changed_stem
        )
        for path in related[:4]:
            add(path)

    for changed in changed_paths:
        parent = PurePosixPath(changed).parent
        siblings = sorted(
            path
            for path in paths
            if path != changed and PurePosixPath(path).parent == parent and eligible(path)
        )
        for path in siblings[:4]:
            add(path)

    for path in sorted(paths):
        parsed = PurePosixPath(path)
        if len(parsed.parts) <= 2 and parsed.name.lower() in REPOSITORY_MANIFEST_NAMES:
            add(path)

    return tuple(selected[:MAX_REPOSITORY_SOURCE_FILES])


def _context_stem(path: str) -> str:
    stem = PurePosixPath(path).stem.lower()
    for prefix in ("test_", "test-", "spec_", "spec-"):
        if stem.startswith(prefix):
            stem = stem[len(prefix) :]
    for suffix in ("_test", "-test", "_spec", "-spec", ".test", ".spec"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return stem


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
