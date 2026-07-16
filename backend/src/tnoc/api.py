from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import orjson
import redis.asyncio as redis
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, StreamingResponse
from prometheus_client import make_asgi_app
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from tnoc.db import create_engine, create_session_factory
from tnoc.domain import (
    ApprovalDecision,
    DashboardSnapshot,
    InventoryResource,
    TelemetryEvent,
    TopologyRelation,
)
from tnoc.observability import (
    configure_observability,
    instrument_database,
    instrument_fastapi,
)
from tnoc.repository import Repository
from tnoc.security import AuthContext, auth_context, require_role
from tnoc.settings import get_settings


class Accepted(BaseModel):
    id: UUID | str
    accepted: bool
    duplicate: bool = False


class KnowledgeIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=1024)
    source_uri: str = Field(min_length=1, max_length=2048)
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_uri")
    @classmethod
    def reject_secret_bearing_source_uri(cls, value: str) -> str:
        parsed = urlparse(value)
        if (
            not parsed.scheme
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "source_uri must be an absolute URI without credentials, query, or fragment"
            )
        return value


class ApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=4096)


def enforce_payload_size(payload: bytes, maximum: int) -> None:
    if len(payload) > maximum:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Payload exceeds configured size limit",
        )


def enforce_observation_time(observed_at: datetime, maximum_future_skew_seconds: int) -> None:
    maximum = datetime.now(UTC).timestamp() + maximum_future_skew_seconds
    if observed_at.timestamp() > maximum:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Observation timestamp exceeds configured future-skew limit",
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = create_engine(settings)
    instrument_database(engine, app.state.tracer_provider)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    yield
    await app.state.redis.aclose()
    await engine.dispose()


settings = get_settings()
app = FastAPI(
    title="T-NOC ChangeGuard API",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)
app.state.tracer_provider = configure_observability(settings, "api")
instrument_fastapi(app, app.state.tracer_provider)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Tenant-ID"],
)
app.mount("/metrics", make_asgi_app())


async def repository(
    request: Request, context: AuthContext = Depends(auth_context)
) -> AsyncIterator[Repository]:
    async with request.app.state.session_factory() as session:
        result = Repository(session, request.app.state.settings)
        await result.set_tenant_scope(context.tenant_id)
        yield result


async def session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as database_session:
        yield database_session


@app.get("/health/live", include_in_schema=False)
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
async def readiness(database_session: AsyncSession = Depends(session)) -> dict[str, str]:
    await database_session.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.post("/v1/telemetry", response_model=Accepted, status_code=status.HTTP_202_ACCEPTED)
async def ingest_telemetry(
    event: TelemetryEvent,
    context: AuthContext = Depends(auth_context),
    repo: Repository = Depends(repository),
) -> Accepted:
    require_role(context, "telemetry:write")
    enforce_payload_size(
        orjson.dumps(event.model_dump(mode="json")), repo.settings.max_ingest_payload_bytes
    )
    enforce_observation_time(event.observed_at, repo.settings.max_observation_future_skew_seconds)
    if event.tenant_id != context.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    inserted = await repo.save_telemetry(event)
    if inserted:
        await repo.enqueue_outbox(
            tenant_id=context.tenant_id,
            topic=repo.settings.telemetry_topic,
            message_key=str(event.id),
            payload={"event_id": str(event.id), "tenant_id": context.tenant_id},
        )
        await repo.append_audit(
            tenant_id=context.tenant_id,
            incident_id=None,
            event_type="telemetry.accepted",
            actor=context.subject,
            payload={"event_id": str(event.id), "source": event.source},
        )
    await repo.session.commit()
    return Accepted(id=event.id, accepted=True, duplicate=not inserted)


@app.put("/v1/inventory/{resource_id}", response_model=Accepted)
async def upsert_inventory(
    resource_id: str,
    resource: InventoryResource,
    context: AuthContext = Depends(auth_context),
    repo: Repository = Depends(repository),
) -> Accepted:
    require_role(context, "inventory:write")
    enforce_payload_size(
        orjson.dumps(resource.model_dump(mode="json")), repo.settings.max_ingest_payload_bytes
    )
    enforce_observation_time(
        resource.observed_at, repo.settings.max_observation_future_skew_seconds
    )
    if resource.id != resource_id or resource.tenant_id != context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Resource identity mismatch"
        )
    await repo.upsert_inventory(resource)
    await repo.append_audit(
        tenant_id=context.tenant_id,
        incident_id=None,
        event_type="inventory.upserted",
        actor=context.subject,
        payload={"resource_id": resource.id, "observed_at": resource.observed_at.isoformat()},
    )
    await repo.session.commit()
    return Accepted(id=resource.id, accepted=True)


@app.post("/v1/topology", response_model=Accepted, status_code=status.HTTP_202_ACCEPTED)
async def upsert_topology(
    relation: TopologyRelation,
    context: AuthContext = Depends(auth_context),
    repo: Repository = Depends(repository),
) -> Accepted:
    require_role(context, "topology:write")
    enforce_payload_size(
        orjson.dumps(relation.model_dump(mode="json")), repo.settings.max_ingest_payload_bytes
    )
    enforce_observation_time(
        relation.observed_at, repo.settings.max_observation_future_skew_seconds
    )
    if relation.tenant_id != context.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    await repo.upsert_topology(relation)
    await repo.append_audit(
        tenant_id=context.tenant_id,
        incident_id=None,
        event_type="topology.upserted",
        actor=context.subject,
        payload={
            "source_id": relation.source_id,
            "target_id": relation.target_id,
            "relation": relation.relation,
            "observed_at": relation.observed_at.isoformat(),
        },
    )
    await repo.session.commit()
    relation_id = hashlib.sha256(
        orjson.dumps(relation.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
    ).hexdigest()
    return Accepted(id=relation_id, accepted=True)


@app.post("/v1/knowledge", response_model=Accepted, status_code=status.HTTP_202_ACCEPTED)
async def ingest_knowledge(
    request_body: KnowledgeIngestRequest,
    context: AuthContext = Depends(auth_context),
    repo: Repository = Depends(repository),
) -> Accepted:
    require_role(context, "knowledge:write")
    if not repo.settings.rag_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RAG ingestion is disabled by configuration",
        )
    enforce_payload_size(
        orjson.dumps(request_body.model_dump(mode="json")),
        repo.settings.max_knowledge_document_bytes,
    )
    digest = hashlib.sha256(request_body.content.encode("utf-8")).hexdigest()
    document_id = await repo.save_knowledge(
        context.tenant_id,
        request_body.title,
        request_body.source_uri,
        digest,
        request_body.content,
        request_body.metadata,
    )
    await repo.enqueue_outbox(
        tenant_id=context.tenant_id,
        topic=repo.settings.knowledge_topic,
        message_key=str(document_id),
        payload={"document_id": str(document_id), "tenant_id": context.tenant_id},
    )
    await repo.append_audit(
        tenant_id=context.tenant_id,
        incident_id=None,
        event_type="knowledge.accepted",
        actor=context.subject,
        payload={
            "document_id": str(document_id),
            "content_sha256": digest,
            "source_uri_sha256": hashlib.sha256(
                request_body.source_uri.encode("utf-8")
            ).hexdigest(),
        },
    )
    await repo.session.commit()
    return Accepted(id=document_id, accepted=True)


@app.get("/v1/dashboard", response_model=DashboardSnapshot)
async def dashboard(
    context: AuthContext = Depends(auth_context),
    repo: Repository = Depends(repository),
) -> DashboardSnapshot:
    require_role(context, "dashboard:read")
    return await repo.dashboard(context.tenant_id)


@app.get("/v1/incidents/{incident_id}")
async def incident_detail(
    incident_id: UUID,
    context: AuthContext = Depends(auth_context),
    repo: Repository = Depends(repository),
) -> dict[str, Any]:
    require_role(context, "incident:read")
    try:
        return await repo.incident_bundle(context.tenant_id, incident_id)
    except NoResultFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found"
        ) from exc


@app.post(
    "/v1/workflows/{thread_id}/decision",
    response_model=Accepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_decision(
    thread_id: str,
    decision_input: ApprovalInput,
    context: AuthContext = Depends(auth_context),
    repo: Repository = Depends(repository),
) -> Accepted:
    require_role(context, "change:approve")
    decision = ApprovalDecision(
        approved=decision_input.approved,
        actor=context.subject,
        plan_hash=decision_input.plan_hash,
        reason=decision_input.reason,
        decided_at=datetime.now(UTC),
    )
    try:
        incident = await repo.claim_pending_approval(
            context.tenant_id, thread_id, decision_input.plan_hash
        )
    except NoResultFound as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No matching pending approval for this tenant, workflow, and plan hash",
        ) from exc
    message_id = await repo.enqueue_outbox(
        tenant_id=context.tenant_id,
        topic=repo.settings.decision_topic,
        message_key=thread_id,
        payload={
            "thread_id": thread_id,
            "tenant_id": context.tenant_id,
            "decision": decision.model_dump(mode="json"),
        },
    )
    await repo.append_audit(
        tenant_id=context.tenant_id,
        incident_id=incident.id,
        event_type="approval.submitted",
        actor=context.subject,
        payload={
            "thread_id": thread_id,
            "approved": decision.approved,
            "plan_hash": decision.plan_hash,
        },
    )
    await repo.session.commit()
    return Accepted(id=message_id, accepted=True)


@app.get("/v1/events")
async def stream_events(
    request: Request,
    context: AuthContext = Depends(auth_context),
) -> StreamingResponse:
    require_role(context, "dashboard:read")
    redis_client = request.app.state.redis
    channel = f"{request.app.state.settings.event_stream_channel}:{context.tenant_id}"

    async def generate() -> AsyncIterator[str]:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel)
        try:
            while not await request.is_disconnected():
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=request.app.state.settings.sse_heartbeat_seconds,
                )
                if message:
                    yield f"data: {message['data']}\n\n"
                else:
                    yield ": heartbeat\n\n"
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(generate(), media_type="text/event-stream")


def run() -> None:
    active = get_settings()
    uvicorn.run("tnoc.api:app", host=active.api_host, port=active.api_port, factory=False)


if __name__ == "__main__":
    run()
