from __future__ import annotations

import re
from collections import defaultdict

from codetrust.models import ChangedFile, ChangedLine

HUNK_RE = re.compile(r"^@@ -(?:\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def parse_unified_diff(text: str) -> list[ChangedFile]:
    """Parse enough unified-diff structure for evidence-backed verification rules."""
    files: dict[str, dict[str, list[ChangedLine]]] = defaultdict(
        lambda: {"added": [], "removed": []}
    )
    current_path: str | None = None
    new_line = 0
    old_line = 0

    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            parts = raw.split()
            current_path = _clean_path(parts[3]) if len(parts) >= 4 else None
            continue
        if raw.startswith("+++ "):
            current_path = _clean_path(raw[4:].strip())
            continue
        if raw.startswith("@@"):
            match = HUNK_RE.match(raw)
            if match:
                new_line = int(match.group(1))
                old_match = re.match(r"^@@ -(\d+)", raw)
                old_line = int(old_match.group(1)) if old_match else 0
            continue
        if not current_path or raw.startswith(("--- ", "\\ No newline")):
            continue
        if raw.startswith("+"):
            files[current_path]["added"].append(
                ChangedLine(current_path, new_line, raw[1:], "added")
            )
            new_line += 1
        elif raw.startswith("-"):
            files[current_path]["removed"].append(
                ChangedLine(current_path, old_line, raw[1:], "removed")
            )
            old_line += 1
        else:
            new_line += 1
            old_line += 1

    return [
        ChangedFile(path=path, added=tuple(lines["added"]), removed=tuple(lines["removed"]))
        for path, lines in files.items()
        if path != "/dev/null"
    ]


def _clean_path(path: str) -> str:
    if path in {"/dev/null", "dev/null"}:
        return "/dev/null"
    return path[2:] if path.startswith(("a/", "b/")) else path
