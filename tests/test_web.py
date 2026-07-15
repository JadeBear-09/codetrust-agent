from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from codetrust.llm import SynthesisError
from codetrust.models import ScopeComparison
from codetrust.repository_scope import RepositoryIntent
from codetrust.web import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/api/health").json() == {"status": "ok", "service": "codetrust"}


def test_config_never_exposes_model_key(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key-that-must-not-leak")
    monkeypatch.setenv("CODETRUST_MODEL", "gemini-test")

    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["model"] == {
        "configured": True,
        "provider": "gemini",
        "model": "gemini-test",
    }
    assert "secret-key-that-must-not-leak" not in response.text


def test_dashboard_is_real_pr_focused_without_hardcoded_demo() -> None:
    dashboard = client.get("/")

    assert dashboard.status_code == 200
    assert "Verify pull request" in dashboard.text
    assert "Evidence-backed findings" in dashboard.text
    assert 'fetch("/api/github"' in dashboard.text
    assert "/api/product-demo" not in dashboard.text
    assert "Real rejected PR" not in dashboard.text
    assert "Checkout resilience" not in dashboard.text
    assert "refunds/authorization.py" not in dashboard.text


def test_dashboard_verifies_diff_and_records_history(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CODETRUST_DATA_DIR", str(tmp_path))
    response = client.post(
        "/api/verify",
        json={
            "ticket": "## Outcome\n- Rename label.\n",
            "diff": (
                "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
                "@@ -1 +1 @@\n-old=1\n+new=1\n"
            ),
            "model_mode": "disabled",
        },
    )

    assert response.status_code == 200
    assert response.json()["verdict"] == "PASS"
    history = client.get("/api/runs").json()["runs"]
    assert history[0]["run_id"] == response.json()["run_id"]


def test_github_request_rejects_manual_scope_override() -> None:
    response = client.post(
        "/api/github",
        json={
            "reference": "https://github.com/acme/payments/pull/42",
            "intent": "## Out of scope\n- Refund authorization behavior.",
            "model_mode": "required",
        },
    )

    assert response.status_code == 422


def test_github_verification_uses_repository_scope_comparison(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CODETRUST_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "codetrust.web.load_pull_request",
        lambda _reference: SimpleNamespace(
            ticket="# Fix timeout\n\nKeep retries idempotent.",
            diff="diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a=1\n+a=2\n",
            repo="acme/app",
            number=7,
            url="https://github.com/acme/app/pull/7",
            base_sha="base",
            head_sha="head",
            state="OPEN",
            author="developer",
        ),
    )
    captured = {}
    monkeypatch.setattr(
        "codetrust.web.resolve_repository_intent",
        lambda _repo, _sha, _diff, _claim, *, offline: RepositoryIntent(
            content=(
                "# Inferred scope from base repository\n\n"
                "## Outcome\n- Keep retries safe.\n\n"
                "## In scope\n- Retry behavior.\n"
            ),
            source={
                "intent_source": "repository-inference",
                "intent_trust": "inferred",
                "scope_evidence_paths": "README.md, a.py",
            },
            comparison=ScopeComparison(
                repository_purpose="Keep retries safe.",
                change_summary="Adjust retry behavior.",
                relationship="aligned",
                distance=10,
                differences=("Retry timing changes.",),
                evidence_paths=("README.md", "a.py"),
            ),
        ),
    )

    def fake_verify(ticket, _diff, *, offline, source, **kwargs):
        captured.update(ticket=ticket, offline=offline, source=source, **kwargs)
        return SimpleNamespace(to_dict=lambda: {"run_id": "ct-test", "source": source})

    monkeypatch.setattr("codetrust.web.verify_change", fake_verify)

    response = client.post(
        "/api/github",
        json={"reference": "acme/app#7", "model_mode": "disabled"},
    )

    assert response.status_code == 200
    assert captured["ticket"].startswith("# Inferred scope")
    assert captured["source"]["intent_source"] == "repository-inference"
    assert captured["scope_comparison"].relationship == "aligned"
    assert captured["scope_comparison"].distance == 10
    assert captured["change_claim"] == "# Fix timeout\n\nKeep retries idempotent."


def test_github_verification_returns_review_when_repository_evidence_is_insufficient(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("CODETRUST_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "codetrust.web.load_pull_request",
        lambda _reference: SimpleNamespace(
            ticket="# PR-authored claim",
            diff="diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a=1\n+a=2\n",
            repo="acme/app",
            number=7,
            url="https://github.com/acme/app/pull/7",
            base_sha="abcdef1234567",
            head_sha="fedcba7654321",
            state="OPEN",
            author="developer",
        ),
    )
    monkeypatch.setattr(
        "codetrust.web.resolve_repository_intent",
        lambda _repo, _sha, _diff, _claim, *, offline: RepositoryIntent(
            content=(
                "# Repository scope unavailable\n\n"
                "## Outcome\n"
                "- Establish behavior from maintained base-repository evidence.\n"
            ),
            source={
                "intent_source": "insufficient-repository-evidence",
                "intent_trust": "insufficient",
                "repository_documents_read": "0",
            },
            questions=("Which base document defines expected behavior?",),
        ),
    )

    response = client.post(
        "/api/github",
        json={"reference": "acme/app#7", "model_mode": "disabled"},
    )

    assert response.status_code == 200
    assert response.json()["verdict"] == "NEEDS_REVIEW"
    assert response.json()["intent"] == "Repository scope not established"
    assert response.json()["source"]["intent_trust"] == "insufficient"
    assert response.json()["unresolved_questions"] == [
        "Which base document defines expected behavior?"
    ]


def test_required_model_failure_returns_explicit_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "codetrust.web.load_pull_request",
        lambda _reference: SimpleNamespace(
            ticket="# Untrusted PR text",
            diff="diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a=1\n+a=2\n",
            repo="acme/app",
            number=7,
            url="https://github.com/acme/app/pull/7",
            base_sha="abcdef1234567",
            head_sha="fedcba7654321",
            state="OPEN",
            author="developer",
        ),
    )
    monkeypatch.setattr(
        "codetrust.web.resolve_repository_intent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            SynthesisError(
                "MODEL_TIMEOUT",
                "Model did not respond before timeout. Verification stopped.",
                provider="gemini",
                model="gemini-3.5-flash",
                attempts=3,
                duration_ms=90_000,
            )
        ),
    )

    response = client.post(
        "/api/github",
        json={
            "reference": "acme/app#7",
            "model_mode": "required",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "MODEL_TIMEOUT"


def test_unknown_run_returns_404(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CODETRUST_DATA_DIR", str(tmp_path))
    response = client.get("/api/runs/ct-missing")
    assert response.status_code == 404
