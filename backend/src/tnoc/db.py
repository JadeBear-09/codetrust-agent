from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tnoc.settings import Settings


class Base(DeclarativeBase):
    pass


class TelemetryEventRecord(Base):
    __tablename__ = "telemetry_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(256), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    service_id: Mapped[str | None] = mapped_column(String(512), index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    correlation_keys: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(128), index=True)

    __table_args__ = (
        Index("ix_telemetry_tenant_observed", "tenant_id", "observed_at"),
        Index("ix_telemetry_tenant_service", "tenant_id", "service_id"),
    )


class InventoryResourceRecord(Base):
    __tablename__ = "inventory_resources"

    id: Mapped[str] = mapped_column(String(512), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    site_id: Mapped[str | None] = mapped_column(String(256), index=True)
    service_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    labels: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    health: Mapped[float | None] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_inventory_tenant_domain", "tenant_id", "domain"),)


class TopologyRelationRecord(Base):
    __tablename__ = "topology_relations"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    relation: Mapped[str] = mapped_column(String(128), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", "target_id", "relation", name="uq_topology_relation"
        ),
        Index("ix_topology_tenant_source", "tenant_id", "source_id"),
        Index("ix_topology_tenant_target", "tenant_id", "target_id"),
    )


class IncidentRecord(Base):
    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    correlation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    service_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    root_cause: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    workflow_thread_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    isolated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_incident_tenant_status_updated", "tenant_id", "status", "updated_at"),
    )


class IncidentEventRecord(Base):
    __tablename__ = "incident_events"

    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    incident_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("telemetry_events.id", ondelete="CASCADE"),
        primary_key=True,
    )


class EvidenceRecord(Base):
    __tablename__ = "evidence"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    incident_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class RemediationRecord(Base):
    __tablename__ = "remediations"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    incident_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    plan: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_decision: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    approval: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "incident_id", "plan_hash", name="uq_remediation_plan"),
    )


class KnowledgeRecord(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "content_sha256", name="uq_knowledge_tenant_hash"),
    )


class AuditRecord(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    incident_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(256), nullable=False)
    actor: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditHeadRecord(Base):
    __tablename__ = "audit_heads"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    record_hash: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboxRecord(Base):
    __tablename__ = "outbox"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    message_key: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(256))

    __table_args__ = (Index("ix_outbox_unpublished", "published_at", "created_at"),)


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=settings.database_pool_recycle_seconds,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
