from __future__ import annotations

from types import SimpleNamespace

from codetrust import cli
from codetrust.models import ScopeComparison, Verdict
from codetrust.repository_scope import RepositoryIntent


def test_cli_github_url_uses_automatic_repository_scope(monkeypatch, tmp_path) -> None:
    captured = {}
    change = SimpleNamespace(
        ticket="# PR title\n\nAuthor claim",
        diff="diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a=1\n+a=2\n",
        repo="acme/app",
        number=7,
        url="https://github.com/acme/app/pull/7",
        base_sha="abcdef1234567",
        head_sha="fedcba7654321",
        state="OPEN",
        author="developer",
    )
    monkeypatch.setattr(cli, "load_pull_request", lambda _reference: change)
    monkeypatch.setattr(
        cli,
        "resolve_repository_intent",
        lambda repo, revision, diff, claim, *, offline: captured.update(
            repo=repo,
            revision=revision,
            diff=diff,
            claim=claim,
            offline=offline,
        )
        or RepositoryIntent(
            content=(
                "# Inferred scope from base repository\n\n"
                "## Outcome\n- Preserve behavior.\n\n"
                "## In scope\n- Application code.\n"
            ),
            source={
                "intent_source": "repository-inference",
                "intent_trust": "inferred",
                "scope_evidence_paths": "README.md",
            },
            comparison=ScopeComparison(
                repository_purpose="Preserve behavior.",
                change_summary="Change application code.",
                relationship="adjacent",
                distance=30,
                evidence_paths=("README.md",),
            ),
        ),
    )

    def fake_verify(ticket, diff, **kwargs):
        captured.update(ticket=ticket, verify_diff=diff, verify_kwargs=kwargs)
        return SimpleNamespace(
            verdict=Verdict.NEEDS_REVIEW,
            risk_score=4,
            findings=[],
        )

    monkeypatch.setattr(cli, "verify_change", fake_verify)
    monkeypatch.setattr(cli, "write_reports", lambda _report, _directory: {})

    result = cli.main(
        [
            "verify",
            "--github-pr",
            "https://github.com/acme/app/pull/7",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert captured["claim"] == "# PR title\n\nAuthor claim"
    assert captured["verify_kwargs"]["change_claim"] == captured["claim"]
    assert captured["verify_kwargs"]["source"]["intent_trust"] == "inferred"
    assert captured["verify_kwargs"]["source"]["reference"] == "acme/app#7"
    assert captured["verify_kwargs"]["scope_comparison"].distance == 30
