from __future__ import annotations

import re
from collections import defaultdict

from codetrust.models import ChangedFile, ImpactArea

AREA_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    ("Payments", "business-domain", "critical", r"payment|billing|wallet|charge|reconcil"),
    ("API contracts", "interface", "high", r"openapi|swagger|\.proto$|graphql|/api/"),
    ("Data layer", "persistence", "high", r"migration|schema|\.sql$|database|repository"),
    ("Async runtime", "runtime", "high", r"async|worker|queue|thread|executor"),
    ("Test safety net", "verification", "medium", r"(^|/)(test_|tests?/|.*_test\.)"),
    ("Deployment", "operations", "high", r"docker|kubernetes|helm|terraform|deploy|workflow"),
    ("Security boundary", "security", "critical", r"auth|token|secret|permission|crypto|security"),
)


def map_impact(files: list[ChangedFile]) -> list[ImpactArea]:
    matches: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for file in files:
        searchable = f"{file.path}\n{file.added_text}\n{file.removed_text}"
        for name, kind, risk, pattern in AREA_PATTERNS:
            if re.search(pattern, searchable, re.I):
                matches[(name, kind, risk)].add(file.path)
    return [
        ImpactArea(name=name, kind=kind, risk=risk, paths=tuple(sorted(paths)))
        for (name, kind, risk), paths in matches.items()
    ]
