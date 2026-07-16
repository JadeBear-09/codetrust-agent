from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from tnoc.sandbox import SandboxProfile, app, controller

CELLS = ["CELL-101", "CELL-102", "CELL-103"]
PLAN_HASH = hashlib.sha256(b"approved-plan").hexdigest()
PROFILE = SandboxProfile.model_validate_json(
    (Path(__file__).parents[1] / "examples/sandbox/ran-capacity-congestion.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    await controller.reset(PROFILE)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://sandbox") as session:
        yield session


def headers(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key, "X-Plan-Hash": PLAN_HASH}


@pytest.mark.asyncio
async def test_failed_change_rolls_back_and_is_independently_verified(
    client: httpx.AsyncClient,
) -> None:
    shift = await client.post(
        "/traffic-shifts",
        json={
            "cell_ids": CELLS,
            "shift_percent": 15,
            "destination_cluster": "CLUSTER-BETA",
        },
        headers=headers("apply-approved-plan-0001"),
    )
    assert shift.status_code == 200
    assert shift.json()["metrics"]["packet_loss_percent"] == 2.8

    verification = await client.get("/verification", params={"cell_ids": CELLS})
    assert verification.status_code == 200
    assert verification.json()["state"] == "degraded"
    assert not verification.json()["within_threshold"]

    rollback = await client.post(
        "/rollbacks",
        json={"cell_ids": CELLS},
        headers=headers("rollback-approved-plan-0001"),
    )
    assert rollback.status_code == 200

    restored = await client.get("/rollback-verification", params={"cell_ids": CELLS})
    assert restored.status_code == 200
    assert restored.json()["state"] == "restored"
    assert restored.json()["restoration_verified"]
    assert restored.json()["metrics"] == PROFILE.baseline_metrics.model_dump(mode="json")


@pytest.mark.asyncio
async def test_duplicate_delivery_changes_network_once(client: httpx.AsyncClient) -> None:
    payload = {
        "cell_ids": CELLS,
        "shift_percent": 15,
        "destination_cluster": "CLUSTER-BETA",
    }
    first = await client.post(
        "/traffic-shifts", json=payload, headers=headers("duplicate-delivery-0001")
    )
    second = await client.post(
        "/traffic-shifts", json=payload, headers=headers("duplicate-delivery-0001")
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["duplicate_suppressed"] is False
    assert second.json()["duplicate_suppressed"] is True
    state = (await client.get("/state")).json()
    assert state["apply_count"] == 1
    assert state["duplicates_suppressed"] == 1


@pytest.mark.asyncio
async def test_idempotency_key_cannot_be_reused_for_different_request(
    client: httpx.AsyncClient,
) -> None:
    first = {
        "cell_ids": CELLS,
        "shift_percent": 15,
        "destination_cluster": "CLUSTER-BETA",
    }
    second = {**first, "shift_percent": 10}
    assert (
        await client.post("/traffic-shifts", json=first, headers=headers("payload-binding-0001"))
    ).status_code == 200
    conflict = await client.post(
        "/traffic-shifts", json=second, headers=headers("payload-binding-0001")
    )
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_controller_rejects_out_of_scope_cells(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/traffic-shifts",
        json={
            "cell_ids": ["CELL-101", "CELL-102", "CELL-999"],
            "shift_percent": 15,
            "destination_cluster": "CLUSTER-BETA",
        },
        headers=headers("out-of-scope-test-0001"),
    )
    assert response.status_code == 409
