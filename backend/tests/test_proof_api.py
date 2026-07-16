from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from tnoc.proof_api import ProofRunService, create_app

ROOT = Path(__file__).parents[1]
INCIDENTS = ROOT / "examples/incidents"


def service(tmp_path: Path) -> ProofRunService:
    return ProofRunService(
        incidents_path=INCIDENTS,
        output_root=tmp_path / "runs",
    )


@pytest.mark.asyncio
async def test_config_exposes_incidents_and_six_agent_live_mode(tmp_path: Path) -> None:
    runner = service(tmp_path)
    transport = httpx.ASGITransport(app=create_app(runner))
    async with httpx.AsyncClient(transport=transport, base_url="http://proof") as client:
        response = await client.get("/v1/proof/config")

    assert response.status_code == 200
    config = response.json()
    assert config["model_calls_per_run"] == 6
    assert config["agents"] == [
        "telemetry",
        "topology",
        "change_history",
        "security",
        "adjudicator",
        "response_planner",
    ]
    assert [item["id"] for item in config["incidents"]] == [
        "ran-capacity-congestion",
        "credential-stuffing-attack",
    ]
    assert all(item["file"].endswith(".json") for item in config["incidents"])


@pytest.mark.asyncio
async def test_live_run_exposes_saved_result_and_downloadable_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-test-key")
    runner = service(tmp_path)

    async def fake_live(run_id: str, model: str, incident_id: str) -> None:
        directory = runner.output_root / run_id
        directory.mkdir(parents=True)
        events = [
            {"observed_at": "2026-07-16T10:00:00+00:00", "event": "mission_started"},
            {
                "observed_at": "2026-07-16T10:00:01+00:00",
                "event": "model_call_completed",
                "model": model,
            },
            {"observed_at": "2026-07-16T10:00:02+00:00", "event": "mission_completed"},
        ]
        (directory / "run.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events),
            encoding="utf-8",
        )
        (directory / "summary.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "input_schema_version": "agent-mission-v1",
                    "execution_mode": "live_gemini_multi_agent",
                    "model": model,
                    "incident": {"id": incident_id},
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(runner, "_run_live", fake_live)
    transport = httpx.ASGITransport(app=create_app(runner))
    async with httpx.AsyncClient(transport=transport, base_url="http://proof") as client:
        response = await client.post(
            "/v1/proof/runs",
            json={
                "mode": "live",
                "model": "gemini-3.1-flash-lite",
                "incident_id": "ran-capacity-congestion",
            },
        )
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        for _ in range(100):
            state = (await client.get(f"/v1/proof/runs/{run_id}")).json()
            if state["status"] in {"completed", "failed"}:
                break
            await asyncio.sleep(0.01)

        log = await client.get(f"/v1/proof/runs/{run_id}/log")
        latest = await client.get("/v1/proof/runs/latest")

    assert state["status"] == "completed"
    assert state["mode"] == "live_gemini_multi_agent"
    assert state["progress"]["completed_model_calls"] == 1
    assert log.status_code == 200
    assert "attachment" in log.headers["content-disposition"]
    assert latest.status_code == 200
    assert latest.json()["run_id"] == run_id


@pytest.mark.asyncio
async def test_live_run_refuses_to_start_without_gemini_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    runner = service(tmp_path)
    transport = httpx.ASGITransport(app=create_app(runner))
    async with httpx.AsyncClient(transport=transport, base_url="http://proof") as client:
        response = await client.post(
            "/v1/proof/runs",
            json={
                "mode": "live",
                "model": "gemini-3.1-flash-lite",
                "incident_id": "ran-capacity-congestion",
            },
        )

    assert response.status_code == 409
    assert "GEMINI_API_KEY" in response.json()["detail"]


@pytest.mark.asyncio
async def test_live_failure_redacts_key_from_state_and_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "AIza-test-secret-must-never-leak"  # noqa: S105 - synthetic redaction fixture
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    runner = service(tmp_path)

    async def fail_live(run_id: str, model: str, incident_id: str) -> None:
        del run_id, model, incident_id
        raise RuntimeError(f"provider rejected credential {secret}")

    monkeypatch.setattr(runner, "_run_live", fail_live)
    transport = httpx.ASGITransport(app=create_app(runner))
    async with httpx.AsyncClient(transport=transport, base_url="http://proof") as client:
        response = await client.post(
            "/v1/proof/runs",
            json={
                "mode": "live",
                "model": "gemini-3.1-flash-lite",
                "incident_id": "ran-capacity-congestion",
            },
        )
        run_id = response.json()["run_id"]
        for _ in range(100):
            state = (await client.get(f"/v1/proof/runs/{run_id}")).json()
            if state["status"] == "failed":
                break
            await asyncio.sleep(0.01)
        log = await client.get(f"/v1/proof/runs/{run_id}/log")

    assert state["status"] == "failed"
    assert secret not in str(state)
    assert secret not in log.text
    assert "[REDACTED]" in log.text
