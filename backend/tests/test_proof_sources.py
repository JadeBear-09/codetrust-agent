from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from tnoc.proof_sources import DEFAULT_SOURCE_TOKENS, create_proof_source_app

CASES = Path("examples/incidents")


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_proof_source_app(CASES)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://proof") as session:
        yield session


@pytest.mark.asyncio
async def test_each_source_credential_reads_only_its_authorized_api(
    client: httpx.AsyncClient,
) -> None:
    token = DEFAULT_SOURCE_TOKENS["telemetry"]
    allowed = await client.get(
        "/v1/telemetry/ran-capacity-congestion",
        headers={"Authorization": f"Bearer {token}"},
    )
    denied = await client.get(
        "/v1/security/ran-capacity-congestion",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert allowed.status_code == 200
    assert allowed.json()["source"] == "telemetry"
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_source_access_log_never_contains_credential_value(
    client: httpx.AsyncClient,
) -> None:
    token = DEFAULT_SOURCE_TOKENS["topology"]
    await client.get(
        "/v1/topology/ran-capacity-congestion",
        headers={"Authorization": f"Bearer {token}"},
    )
    state = (await client.get("/state")).json()

    assert state["access_count"] == 1
    assert state["access_log"][0]["credential_role"] == "topology"
    assert token not in str(state)
