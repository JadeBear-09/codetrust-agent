from fastapi.testclient import TestClient

from codetrust.web import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/api/health").json() == {"status": "ok", "service": "codetrust"}


def test_dashboard_verifies_diff() -> None:
    response = client.post(
        "/api/verify",
        json={
            "ticket": "Rename label",
            "diff": "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old=1\n+new=1\n",
            "offline": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["verdict"] == "PASS"
