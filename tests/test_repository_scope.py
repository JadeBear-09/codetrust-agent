from __future__ import annotations

from codetrust.github import RepositoryContext, RepositoryDocument
from codetrust.llm import ScopeInference
from codetrust.repository_scope import resolve_repository_intent

DIFF = (
    "diff --git a/src/payments/retry.py b/src/payments/retry.py\n"
    "--- a/src/payments/retry.py\n"
    "+++ b/src/payments/retry.py\n"
    "@@ -1 +1 @@\n-old\n+new\n"
)


def test_repository_evidence_produces_scope_comparison(monkeypatch) -> None:
    context = RepositoryContext(
        documents=(RepositoryDocument("README.md", "Retry behavior", "doc-hash"),),
        structure=("src/payments/retry.py",),
        sha256="context-hash",
    )
    captured = {}
    monkeypatch.setattr(
        "codetrust.repository_scope.load_repository_context",
        lambda _repo, _revision, paths: captured.update(paths=paths) or context,
    )
    monkeypatch.setattr(
        "codetrust.repository_scope.infer_repository_scope",
        lambda _context, claim, _diff, *, offline: captured.update(
            claim=claim,
            offline=offline,
        )
        or ScopeInference(
            status="sufficient",
            intent=(
                "# Inferred scope from base repository\n\n"
                "## Outcome\n- Preserve retry safety.\n\n"
                "## In scope\n- Retry behavior.\n"
            ),
            confidence="high",
            evidence_paths=("README.md",),
            rationale="README defines retry behavior.",
            model="gemini-test",
            attempts=1,
            duration_ms=15,
            repository_purpose="Preserve retry safety.",
            change_summary="Adjust retry behavior.",
            relationship="aligned",
            distance=14,
            differences=("Retry implementation changes.",),
        ),
    )

    result = resolve_repository_intent(
        "acme/payments",
        "abcdef1234567",
        DIFF,
        "# PR author claim",
        offline=False,
    )

    assert captured["paths"] == ("src/payments/retry.py",)
    assert captured["claim"] == "# PR author claim"
    assert result.source["intent_source"] == "repository-inference"
    assert result.source["intent_trust"] == "inferred"
    assert result.source["scope_evidence_paths"] == "README.md"
    assert result.comparison is not None
    assert result.comparison.relationship == "aligned"
    assert result.comparison.distance == 14
    assert "approved" not in result.content.lower()


def test_insufficient_repository_evidence_returns_review_scope(monkeypatch) -> None:
    context = RepositoryContext((), ("src/payments/retry.py",), "context-hash")
    monkeypatch.setattr(
        "codetrust.repository_scope.load_repository_context",
        lambda _repo, _revision, _paths: context,
    )

    result = resolve_repository_intent(
        "acme/payments",
        "abcdef1234567",
        DIFF,
        "# PR author claim",
        offline=False,
    )

    assert result.source["intent_source"] == "insufficient-repository-evidence"
    assert result.source["intent_trust"] == "insufficient"
    assert result.questions
    assert "PR author claim" not in result.content
