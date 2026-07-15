from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

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
            "ticket": "Rename label",
            "diff": (
                "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
                "@@ -1 +1 @@\n-old=1\n+new=1\n"
            ),
            "offline": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["verdict"] == "PASS"
    history = client.get("/api/runs").json()["runs"]
    assert history[0]["run_id"] == response.json()["run_id"]


def test_github_verification_uses_supplied_intent_and_model(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CODETRUST_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "codetrust.web.load_pull_request",
        lambda _reference: SimpleNamespace(
            ticket="# Pull request title\n\nPR description",
            diff=(
                "diff --git a/refunds/authorization.py b/refunds/authorization.py\n"
                "--- a/refunds/authorization.py\n"
                "+++ b/refunds/authorization.py\n"
                "@@ -1 +1 @@\n-old = 30\n+new = 7\n"
            ),
            repo="acme/payments",
            number=42,
            url="https://github.com/acme/payments/pull/42",
            base_sha="base",
            head_sha="head",
            state="OPEN",
            author="developer",
        ),
    )
    captured = {}

    def fake_verify(ticket, diff, *, offline, source):
        captured.update(ticket=ticket, diff=diff, offline=offline, source=source)
        return SimpleNamespace(
            to_dict=lambda: {
                "run_id": "ct-test",
                "created_at": "2026-07-15T00:00:00+00:00",
                "intent": "Protect refund policy",
                "verdict": "BLOCK",
                "risk_score": 100,
                "summary": "Scope drift",
                "files_changed": 1,
                "findings": [],
                "checks": [],
                "unresolved_questions": [],
                "timeline": [],
                "impact_areas": [],
                "adversarial_tests": [],
                "source": source,
                "model_used": "gemini-test",
                "evidence_hash": "hash",
                "intent_snapshot": None,
                "interpretations": [],
                "alignments": [],
                "scope_coverage": 0,
                "scope_drift": 100,
            }
        )

    monkeypatch.setattr("codetrust.web.verify_change", fake_verify)

    response = client.post(
        "/api/github",
        json={
            "reference": "https://github.com/acme/payments/pull/42",
            "intent": "## Out of scope\n- Refund authorization behavior.",
            "offline": False,
        },
    )

    assert response.status_code == 200
    assert captured["ticket"] == "## Out of scope\n- Refund authorization behavior."
    assert captured["offline"] is False
    assert captured["source"]["reference"] == "acme/payments#42"
    assert captured["source"]["intent_source"] == "provided"
    assert response.json()["model_used"] == "gemini-test"


def test_github_verification_falls_back_to_pr_description(monkeypatch, tmp_path) -> None:
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

    def fake_verify(ticket, _diff, *, offline, source):
        captured.update(ticket=ticket, offline=offline, source=source)
        return SimpleNamespace(to_dict=lambda: {"run_id": "ct-test", "source": source})

    monkeypatch.setattr("codetrust.web.verify_change", fake_verify)

    response = client.post("/api/github", json={"reference": "acme/app#7", "offline": True})

    assert response.status_code == 200
    assert captured["ticket"] == "# Fix timeout\n\nKeep retries idempotent."
    assert captured["source"]["intent_source"] == "pull-request"


def test_unknown_run_returns_404(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CODETRUST_DATA_DIR", str(tmp_path))
    response = client.get("/api/runs/ct-missing")
    assert response.status_code == 404
