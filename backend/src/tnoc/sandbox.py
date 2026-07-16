from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

PLAN_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class NetworkMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    traffic_load_percent: float = Field(ge=0, le=100)
    packet_loss_percent: float = Field(ge=0, le=100)
    latency_ms: float = Field(ge=0)


class VerificationThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_packet_loss_percent: float = Field(ge=0, le=100)
    max_latency_ms: float = Field(ge=0)


class SandboxProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(min_length=3, max_length=128)
    resource_ids: list[str] = Field(min_length=1, max_length=100)
    baseline_metrics: NetworkMetrics
    post_change_metrics: NetworkMetrics
    verification_thresholds: VerificationThresholds


class TrafficShift(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_ids: list[str] = Field(min_length=1, max_length=100)
    shift_percent: int = Field(gt=0, le=100)
    destination_cluster: str = Field(pattern=r"^CLUSTER-[A-Z0-9-]+$")


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_ids: list[str] = Field(min_length=1, max_length=100)


class SandboxController:
    """Mutable, process-local controller used only for the labelled demo environment."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._responses: dict[str, tuple[str, dict[str, Any]]] = {}
        self.profile: SandboxProfile | None = None
        self.reset_unlocked(None)

    def reset_unlocked(self, profile: SandboxProfile | None) -> None:
        self.profile = profile
        self.revision = 1
        self.metrics = profile.baseline_metrics.model_dump(mode="json") if profile else {}
        self.shifted_percent = 0
        self.destination_cluster: str | None = None
        self.apply_count = 0
        self.rollback_count = 0
        self.duplicates_suppressed = 0
        self.timeline: list[dict[str, Any]] = []
        self._responses = {}

    async def reset(self, profile: SandboxProfile) -> dict[str, Any]:
        async with self._lock:
            self.reset_unlocked(profile)
            return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "scenario": self.profile.incident_id if self.profile else None,
            "configured": self.profile is not None,
            "sandbox": True,
            "revision": self.revision,
            "cell_ids": list(self.profile.resource_ids) if self.profile else [],
            "metrics": deepcopy(self.metrics),
            "shifted_percent": self.shifted_percent,
            "destination_cluster": self.destination_cluster,
            "apply_count": self.apply_count,
            "rollback_count": self.rollback_count,
            "duplicates_suppressed": self.duplicates_suppressed,
            "timeline": deepcopy(self.timeline),
        }

    @staticmethod
    def _digest(payload: BaseModel, plan_hash: str) -> str:
        encoded = json.dumps(
            {"payload": payload.model_dump(mode="json"), "plan_hash": plan_hash},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _validate_scope(self, cell_ids: list[str]) -> None:
        if self.profile is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sandbox profile is not configured",
            )
        expected = self.profile.resource_ids
        if set(cell_ids) != set(expected) or len(cell_ids) != len(expected):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Requested cells do not exactly match sandbox incident scope",
            )

    @staticmethod
    def _validate_headers(idempotency_key: str, plan_hash: str) -> None:
        if len(idempotency_key) < 16:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Idempotency-Key must contain at least 16 characters",
            )
        if not PLAN_HASH_PATTERN.fullmatch(plan_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Plan-Hash must be a lowercase SHA-256 digest",
            )

    def _replay(self, key: str, digest: str) -> dict[str, Any] | None:
        cached = self._responses.get(key)
        if cached is None:
            return None
        cached_digest, response = cached
        if cached_digest != digest:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key was already used with a different request",
            )
        self.duplicates_suppressed += 1
        replay = deepcopy(response)
        replay["duplicate_suppressed"] = True
        replay["duplicates_suppressed"] = self.duplicates_suppressed
        return replay

    async def shift(
        self, request: TrafficShift, idempotency_key: str, plan_hash: str
    ) -> dict[str, Any]:
        self._validate_scope(request.cell_ids)
        self._validate_headers(idempotency_key, plan_hash)
        digest = self._digest(request, plan_hash)
        async with self._lock:
            replay = self._replay(idempotency_key, digest)
            if replay is not None:
                return replay
            if self.shifted_percent:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Traffic shift is already active",
                )
            self.revision += 1
            self.shifted_percent = request.shift_percent
            self.destination_cluster = request.destination_cluster
            self.apply_count += 1
            if self.profile is None:
                raise RuntimeError("Sandbox profile disappeared")
            self.metrics = self.profile.post_change_metrics.model_dump(mode="json")
            event = {
                "event": "traffic_shift_applied",
                "revision": self.revision,
                "plan_hash": plan_hash,
                "observed_at": datetime.now(UTC).isoformat(),
            }
            self.timeline.append(event)
            response = {
                "accepted": True,
                "sandbox": True,
                "revision": self.revision,
                "apply_count": self.apply_count,
                "duplicate_suppressed": False,
                "metrics": deepcopy(self.metrics),
            }
            self._responses[idempotency_key] = (digest, deepcopy(response))
            return response

    async def rollback(
        self, request: RollbackRequest, idempotency_key: str, plan_hash: str
    ) -> dict[str, Any]:
        self._validate_scope(request.cell_ids)
        self._validate_headers(idempotency_key, plan_hash)
        digest = self._digest(request, plan_hash)
        async with self._lock:
            replay = self._replay(idempotency_key, digest)
            if replay is not None:
                return replay
            if not self.shifted_percent:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="No active traffic shift to roll back",
                )
            self.revision += 1
            if self.profile is None:
                raise RuntimeError("Sandbox profile disappeared")
            self.metrics = self.profile.baseline_metrics.model_dump(mode="json")
            self.shifted_percent = 0
            self.destination_cluster = None
            self.rollback_count += 1
            event = {
                "event": "rollback_applied",
                "revision": self.revision,
                "plan_hash": plan_hash,
                "observed_at": datetime.now(UTC).isoformat(),
            }
            self.timeline.append(event)
            response = {
                "accepted": True,
                "sandbox": True,
                "revision": self.revision,
                "rollback_count": self.rollback_count,
                "duplicate_suppressed": False,
                "metrics": deepcopy(self.metrics),
            }
            self._responses[idempotency_key] = (digest, deepcopy(response))
            return response

    async def verify_change(self, cell_ids: list[str]) -> dict[str, Any]:
        self._validate_scope(cell_ids)
        async with self._lock:
            if self.profile is None:
                raise RuntimeError("Sandbox profile disappeared")
            thresholds = self.profile.verification_thresholds
            within_threshold = (
                self.metrics["packet_loss_percent"] <= thresholds.max_packet_loss_percent
                and self.metrics["latency_ms"] <= thresholds.max_latency_ms
            )
            return {
                "state": "healthy" if within_threshold else "degraded",
                "within_threshold": within_threshold,
                "sandbox": True,
                "revision": self.revision,
                "metrics": deepcopy(self.metrics),
            }

    async def verify_rollback(self, cell_ids: list[str]) -> dict[str, Any]:
        self._validate_scope(cell_ids)
        async with self._lock:
            if self.profile is None:
                raise RuntimeError("Sandbox profile disappeared")
            baseline = self.profile.baseline_metrics.model_dump(mode="json")
            restored = self.metrics == baseline and self.shifted_percent == 0
            return {
                "state": "restored" if restored else "not_restored",
                "restoration_verified": restored,
                "sandbox": True,
                "revision": self.revision,
                "metrics": deepcopy(self.metrics),
            }


controller = SandboxController()
app = FastAPI(
    title="T-NOC ChangeGuard Telecom Sandbox",
    version="1.0.0",
    description="Non-production mutable controller for proof-carrying change demonstrations.",
)


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": "sandbox"}


@app.get("/state")
async def read_state() -> dict[str, Any]:
    return controller.snapshot()


@app.post("/reset")
async def reset_state(profile: SandboxProfile) -> dict[str, Any]:
    return await controller.reset(profile)


@app.post("/traffic-shifts")
async def shift_traffic(
    request: TrafficShift,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    plan_hash: str = Header(alias="X-Plan-Hash"),
) -> dict[str, Any]:
    return await controller.shift(request, idempotency_key, plan_hash)


@app.get("/verification")
async def verify_change(
    cell_ids: list[str] = Query(min_length=1, max_length=100),
) -> dict[str, Any]:
    return await controller.verify_change(cell_ids)


@app.post("/rollbacks")
async def rollback_change(
    request: RollbackRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    plan_hash: str = Header(alias="X-Plan-Hash"),
) -> dict[str, Any]:
    return await controller.rollback(request, idempotency_key, plan_hash)


@app.get("/rollback-verification")
async def verify_rollback(
    cell_ids: list[str] = Query(min_length=1, max_length=100),
) -> dict[str, Any]:
    return await controller.verify_rollback(cell_ids)


def run() -> None:
    if os.environ.get("ENVIRONMENT") == "production":
        raise RuntimeError("Sandbox controller refuses to start in production")
    host = os.environ.get("SANDBOX_HOST", "127.0.0.1")
    port = int(os.environ.get("SANDBOX_PORT", "8090"))
    uvicorn.run("tnoc.sandbox:app", host=host, port=port, factory=False)


if __name__ == "__main__":
    run()
