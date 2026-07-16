from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import orjson
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from tnoc.db import (
    AuditHeadRecord,
    AuditRecord,
    EvidenceRecord,
    IncidentEventRecord,
    IncidentRecord,
    InventoryResourceRecord,
    KnowledgeRecord,
    OutboxRecord,
    RemediationRecord,
    TelemetryEventRecord,
    TopologyRelationRecord,
)
from tnoc.domain import (
    DashboardSnapshot,
    Domain,
    Evidence,
    IncidentStatus,
    IncidentSummary,
    InventoryResource,
    PolicyDecision,
    RemediationPlan,
    Severity,
    TelemetryEvent,
    ToolResult,
    TopologyRelation,
)
from tnoc.settings import Settings
from tnoc.tools import plan_hash

OPEN_STATUSES = {
    IncidentStatus.OPEN.value,
    IncidentStatus.INVESTIGATING.value,
    IncidentStatus.AWAITING_APPROVAL.value,
    IncidentStatus.DECISION_SUBMITTED.value,
    IncidentStatus.EXECUTING.value,
    IncidentStatus.VERIFYING.value,
}

SEVERITY_RANK = {
    Severity.INFO.value: 0,
    Severity.WARNING.value: 1,
    Severity.MINOR.value: 2,
    Severity.MAJOR.value: 3,
    Severity.CRITICAL.value: 4,
}


class Repository:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def set_tenant_scope(self, tenant_id: str) -> None:
        await self.session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )

    async def save_telemetry(self, event: TelemetryEvent) -> bool:
        statement = (
            insert(TelemetryEventRecord)
            .values(
                id=event.id,
                tenant_id=event.tenant_id,
                source=event.source,
                domain=event.domain.value,
                event_type=event.event_type,
                observed_at=event.observed_at,
                received_at=datetime.now(UTC),
                severity=event.severity.value,
                resource_id=event.resource_id,
                service_id=event.service_id,
                summary=event.summary,
                attributes=event.attributes,
                correlation_keys=event.correlation_keys,
                trace_id=event.trace_id,
            )
            .on_conflict_do_nothing(index_elements=[TelemetryEventRecord.id])
            .returning(TelemetryEventRecord.id)
        )
        inserted = (await self.session.execute(statement)).scalar_one_or_none()
        if inserted is not None:
            evidence = Evidence(
                id=event.id,
                kind="telemetry",
                source=event.source,
                statement=event.summary,
                observed_at=event.observed_at,
                payload=event.model_dump(mode="json"),
            )
            await self._save_evidence_record(event.tenant_id, None, evidence)
        return inserted is not None

    async def upsert_inventory(self, resource: InventoryResource) -> None:
        values = {
            "id": resource.id,
            "tenant_id": resource.tenant_id,
            "domain": resource.domain.value,
            "kind": resource.kind,
            "name": resource.name,
            "site_id": resource.site_id,
            "service_ids": resource.service_ids,
            "labels": resource.labels,
            "health": resource.health,
            "observed_at": resource.observed_at,
        }
        statement = insert(InventoryResourceRecord).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[InventoryResourceRecord.id, InventoryResourceRecord.tenant_id],
            set_={key: value for key, value in values.items() if key not in {"id", "tenant_id"}},
            where=statement.excluded.observed_at >= InventoryResourceRecord.observed_at,
        )
        await self.session.execute(statement)

    async def upsert_topology(self, relation: TopologyRelation) -> None:
        values = {
            "tenant_id": relation.tenant_id,
            "source_id": relation.source_id,
            "target_id": relation.target_id,
            "relation": relation.relation,
            "attributes": relation.attributes,
            "observed_at": relation.observed_at,
        }
        statement = insert(TopologyRelationRecord).values(**values)
        statement = statement.on_conflict_do_update(
            constraint="uq_topology_relation",
            set_={
                "attributes": statement.excluded.attributes,
                "observed_at": statement.excluded.observed_at,
            },
            where=statement.excluded.observed_at >= TopologyRelationRecord.observed_at,
        )
        await self.session.execute(statement)

    async def correlate_event(self, event: TelemetryEvent) -> tuple[IncidentRecord, bool, bool]:
        fingerprint_payload = {
            "tenant_id": event.tenant_id,
            "service_id": event.service_id,
            "resource_id": None if event.service_id else event.resource_id,
            "correlation_keys": dict(sorted(event.correlation_keys.items())),
        }
        fingerprint = hashlib.sha256(
            orjson.dumps(fingerprint_payload, option=orjson.OPT_SORT_KEYS)
        ).hexdigest()
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:fingerprint, 0))"),
            {"fingerprint": fingerprint},
        )
        cutoff = event.observed_at - timedelta(seconds=self.settings.correlation_window_seconds)
        query = (
            select(IncidentRecord)
            .where(
                IncidentRecord.tenant_id == event.tenant_id,
                IncidentRecord.correlation_fingerprint == fingerprint,
                IncidentRecord.status.in_(OPEN_STATUSES),
                IncidentRecord.updated_at >= cutoff,
            )
            .order_by(IncidentRecord.updated_at.desc())
            .limit(1)
            .with_for_update()
        )
        incident = (await self.session.execute(query)).scalar_one_or_none()
        created = incident is None
        if incident is None:
            incident = IncidentRecord(
                tenant_id=event.tenant_id,
                correlation_fingerprint=fingerprint,
                status=IncidentStatus.OPEN.value,
                severity=event.severity.value,
                title=event.summary[:1024],
                summary=event.summary,
                service_ids=[event.service_id] if event.service_id else [],
                event_count=0,
                opened_at=event.observed_at,
                updated_at=event.observed_at,
            )
            self.session.add(incident)
            await self.session.flush()

        association = (
            insert(IncidentEventRecord)
            .values(tenant_id=event.tenant_id, incident_id=incident.id, event_id=event.id)
            .on_conflict_do_nothing()
            .returning(IncidentEventRecord.event_id)
        )
        linked = (await self.session.execute(association)).scalar_one_or_none()
        if linked is not None:
            incident.event_count += 1
            incident.updated_at = max(incident.updated_at, event.observed_at)
            if SEVERITY_RANK[event.severity.value] > SEVERITY_RANK[incident.severity]:
                incident.severity = event.severity.value
            if event.service_id and event.service_id not in incident.service_ids:
                incident.service_ids = [*incident.service_ids, event.service_id]
        should_investigate = (
            linked is not None and incident.event_count == self.settings.correlation_min_event_count
        )
        if (
            incident.event_count >= self.settings.correlation_min_event_count
            and incident.status
            in {
                IncidentStatus.OPEN.value,
                IncidentStatus.INVESTIGATING.value,
            }
        ):
            incident.status = IncidentStatus.INVESTIGATING.value
            if incident.workflow_thread_id is None:
                incident.workflow_thread_id = str(incident.id)

        await self.session.execute(
            update(EvidenceRecord)
            .where(EvidenceRecord.id == event.id)
            .values(incident_id=incident.id)
        )
        return incident, created, should_investigate

    async def get_event(self, event_id: UUID) -> TelemetryEvent:
        record = (
            await self.session.execute(
                select(TelemetryEventRecord).where(TelemetryEventRecord.id == event_id)
            )
        ).scalar_one()
        return TelemetryEvent(
            id=record.id,
            tenant_id=record.tenant_id,
            source=record.source,
            domain=Domain(record.domain),
            event_type=record.event_type,
            observed_at=record.observed_at,
            severity=Severity(record.severity),
            resource_id=record.resource_id,
            service_id=record.service_id,
            summary=record.summary,
            attributes=record.attributes,
            correlation_keys=record.correlation_keys,
            trace_id=record.trace_id,
        )

    async def incident_bundle(self, tenant_id: str, incident_id: UUID) -> dict[str, Any]:
        incident = (
            await self.session.execute(
                select(IncidentRecord).where(
                    IncidentRecord.id == incident_id, IncidentRecord.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        events = (
            (
                await self.session.execute(
                    select(TelemetryEventRecord)
                    .join(
                        IncidentEventRecord, IncidentEventRecord.event_id == TelemetryEventRecord.id
                    )
                    .where(IncidentEventRecord.incident_id == incident_id)
                    .order_by(TelemetryEventRecord.observed_at.desc())
                    .limit(self.settings.max_context_events)
                )
            )
            .scalars()
            .all()
        )
        evidence = (
            (
                await self.session.execute(
                    select(EvidenceRecord)
                    .where(EvidenceRecord.incident_id == incident_id)
                    .order_by(EvidenceRecord.observed_at.desc())
                    .limit(self.settings.max_context_evidence)
                )
            )
            .scalars()
            .all()
        )
        resource_ids = {event.resource_id for event in events}
        topology: list[TopologyRelationRecord] = []
        if resource_ids:
            topology = list(
                (
                    await self.session.execute(
                        select(TopologyRelationRecord).where(
                            TopologyRelationRecord.tenant_id == tenant_id,
                            or_(
                                TopologyRelationRecord.source_id.in_(resource_ids),
                                TopologyRelationRecord.target_id.in_(resource_ids),
                            ),
                        )
                    )
                )
                .scalars()
                .all()
            )
        remediation = (
            await self.session.execute(
                select(RemediationRecord)
                .where(
                    RemediationRecord.tenant_id == tenant_id,
                    RemediationRecord.incident_id == incident_id,
                )
                .order_by(RemediationRecord.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return {
            "incident": self._incident_dict(incident),
            "events": [self._event_dict(event) for event in events],
            "evidence": [self._evidence_dict(item) for item in evidence],
            "topology": [self._topology_dict(item) for item in topology],
            "remediation": self._remediation_dict(remediation) if remediation else None,
        }

    async def save_root_cause(
        self, tenant_id: str, incident_id: UUID, root_cause: str, confidence: float
    ) -> None:
        incident = (
            await self.session.execute(
                select(IncidentRecord)
                .where(IncidentRecord.id == incident_id, IncidentRecord.tenant_id == tenant_id)
                .with_for_update()
            )
        ).scalar_one()
        incident.root_cause = root_cause
        incident.confidence = confidence
        incident.isolated_at = datetime.now(UTC)
        incident.updated_at = datetime.now(UTC)

    async def save_remediation(
        self,
        tenant_id: str,
        incident_id: UUID,
        plan: RemediationPlan,
        policy: PolicyDecision,
        status: str,
        results: list[ToolResult] | None = None,
        approval: dict[str, Any] | None = None,
    ) -> UUID:
        now = datetime.now(UTC)
        current_plan_hash = plan_hash(plan)
        statement = (
            insert(RemediationRecord)
            .values(
                id=uuid4(),
                tenant_id=tenant_id,
                incident_id=incident_id,
                plan=plan.model_dump(mode="json"),
                plan_hash=current_plan_hash,
                policy_decision=policy.model_dump(mode="json"),
                approval=approval,
                status=status,
                results=[item.model_dump(mode="json") for item in results or []],
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_remediation_plan",
                set_={
                    "policy_decision": policy.model_dump(mode="json"),
                    "approval": approval,
                    "status": status,
                    "results": [item.model_dump(mode="json") for item in results or []],
                    "updated_at": now,
                },
            )
            .returning(RemediationRecord.id)
        )
        return (await self.session.execute(statement)).scalar_one()

    async def set_incident_status(
        self, tenant_id: str, incident_id: UUID, status: IncidentStatus
    ) -> None:
        incident = (
            await self.session.execute(
                select(IncidentRecord)
                .where(IncidentRecord.id == incident_id, IncidentRecord.tenant_id == tenant_id)
                .with_for_update()
            )
        ).scalar_one()
        incident.status = status.value
        incident.updated_at = datetime.now(UTC)
        if status is IncidentStatus.RESOLVED:
            incident.resolved_at = incident.updated_at

    async def incident_status(self, tenant_id: str, incident_id: UUID) -> IncidentStatus:
        value = (
            await self.session.execute(
                select(IncidentRecord.status).where(
                    IncidentRecord.id == incident_id,
                    IncidentRecord.tenant_id == tenant_id,
                )
            )
        ).scalar_one()
        return IncidentStatus(value)

    async def claim_pending_approval(
        self, tenant_id: str, thread_id: str, expected_plan_hash: str
    ) -> IncidentRecord:
        incident, remediation = (
            await self.session.execute(
                select(IncidentRecord, RemediationRecord)
                .join(RemediationRecord, RemediationRecord.incident_id == IncidentRecord.id)
                .where(
                    IncidentRecord.tenant_id == tenant_id,
                    IncidentRecord.workflow_thread_id == thread_id,
                    IncidentRecord.status == IncidentStatus.AWAITING_APPROVAL.value,
                    RemediationRecord.plan_hash == expected_plan_hash,
                    RemediationRecord.status == IncidentStatus.AWAITING_APPROVAL.value,
                )
                .with_for_update()
            )
        ).one()
        incident.status = IncidentStatus.DECISION_SUBMITTED.value
        incident.updated_at = datetime.now(UTC)
        remediation.status = IncidentStatus.DECISION_SUBMITTED.value
        remediation.updated_at = incident.updated_at
        return cast(IncidentRecord, incident)

    async def approval_replay_status(
        self, tenant_id: str, thread_id: str, expected_plan_hash: str
    ) -> IncidentStatus:
        value = (
            await self.session.execute(
                select(IncidentRecord.status)
                .join(RemediationRecord, RemediationRecord.incident_id == IncidentRecord.id)
                .where(
                    IncidentRecord.tenant_id == tenant_id,
                    IncidentRecord.workflow_thread_id == thread_id,
                    IncidentRecord.status.in_(
                        {
                            IncidentStatus.DECISION_SUBMITTED.value,
                            IncidentStatus.EXECUTING.value,
                            IncidentStatus.VERIFYING.value,
                            IncidentStatus.RESOLVED.value,
                            IncidentStatus.REJECTED.value,
                            IncidentStatus.FAILED.value,
                        }
                    ),
                    RemediationRecord.plan_hash == expected_plan_hash,
                )
            )
        ).scalar_one()
        return IncidentStatus(value)

    async def append_audit(
        self,
        *,
        tenant_id: str,
        incident_id: UUID | None,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
    ) -> str:
        now = datetime.now(UTC)
        head = (
            await self.session.execute(
                select(AuditHeadRecord)
                .where(AuditHeadRecord.tenant_id == tenant_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if head is None:
            await self.session.execute(
                insert(AuditHeadRecord)
                .values(tenant_id=tenant_id, record_hash=None, updated_at=now)
                .on_conflict_do_nothing(index_elements=[AuditHeadRecord.tenant_id])
            )
            head = (
                await self.session.execute(
                    select(AuditHeadRecord)
                    .where(AuditHeadRecord.tenant_id == tenant_id)
                    .with_for_update()
                )
            ).scalar_one()
        body = {
            "tenant_id": tenant_id,
            "incident_id": str(incident_id) if incident_id else None,
            "event_type": event_type,
            "actor": actor,
            "payload": payload,
            "previous_hash": head.record_hash,
            "created_at": now.isoformat(),
        }
        record_hash = hashlib.sha256(orjson.dumps(body, option=orjson.OPT_SORT_KEYS)).hexdigest()
        self.session.add(
            AuditRecord(
                tenant_id=tenant_id,
                incident_id=incident_id,
                event_type=event_type,
                actor=actor,
                payload=payload,
                previous_hash=head.record_hash,
                record_hash=record_hash,
                created_at=now,
            )
        )
        head.record_hash = record_hash
        head.updated_at = now
        return record_hash

    async def save_knowledge(
        self,
        tenant_id: str,
        title: str,
        source_uri: str,
        content_sha256: str,
        content: str,
        metadata: dict[str, Any],
    ) -> UUID:
        statement = (
            insert(KnowledgeRecord)
            .values(
                tenant_id=tenant_id,
                title=title,
                source_uri=source_uri,
                content_sha256=content_sha256,
                content=content,
                metadata_=metadata,
                active=True,
                created_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                constraint="uq_knowledge_tenant_hash",
                set_={
                    "active": True,
                    "metadata": metadata,
                    "title": title,
                    "source_uri": source_uri,
                    "content": content,
                },
            )
            .returning(KnowledgeRecord.id)
        )
        return (await self.session.execute(statement)).scalar_one()

    async def get_knowledge(self, tenant_id: str, document_id: UUID) -> KnowledgeRecord:
        return (
            await self.session.execute(
                select(KnowledgeRecord).where(
                    KnowledgeRecord.id == document_id,
                    KnowledgeRecord.tenant_id == tenant_id,
                    KnowledgeRecord.active.is_(True),
                )
            )
        ).scalar_one()

    async def enqueue_outbox(
        self, *, tenant_id: str, topic: str, message_key: str, payload: dict[str, Any]
    ) -> UUID:
        message_id = UUID(payload["message_id"]) if payload.get("message_id") else uuid4()
        payload = {**payload, "message_id": str(message_id)}
        record = OutboxRecord(
            id=message_id,
            tenant_id=tenant_id,
            topic=topic,
            message_key=message_key,
            payload=payload,
            created_at=datetime.now(UTC),
            published_at=None,
            attempts=0,
            last_error=None,
        )
        self.session.add(record)
        await self.session.flush()
        return record.id

    async def claim_outbox(self, limit: int) -> list[OutboxRecord]:
        return list(
            (
                await self.session.execute(
                    select(OutboxRecord)
                    .where(OutboxRecord.published_at.is_(None))
                    .order_by(OutboxRecord.created_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )

    async def mark_outbox_published(self, record: OutboxRecord) -> None:
        record.published_at = datetime.now(UTC)
        record.attempts += 1
        record.last_error = None

    async def mark_outbox_failed(self, record: OutboxRecord, error_type: str) -> None:
        record.attempts += 1
        record.last_error = error_type[:256]

    async def dashboard(self, tenant_id: str) -> DashboardSnapshot:
        now = datetime.now(UTC)
        event_cutoff = now - timedelta(seconds=self.settings.dashboard_window_seconds)
        rate_cutoff = now - timedelta(seconds=self.settings.dashboard_rate_window_seconds)

        managed_assets, service_health = (
            await self.session.execute(
                select(
                    func.count(InventoryResourceRecord.id), func.avg(InventoryResourceRecord.health)
                ).where(InventoryResourceRecord.tenant_id == tenant_id)
            )
        ).one()
        active_alarms = (
            await self.session.execute(
                select(func.count(TelemetryEventRecord.id)).where(
                    TelemetryEventRecord.tenant_id == tenant_id,
                    TelemetryEventRecord.observed_at >= event_cutoff,
                    TelemetryEventRecord.severity != Severity.INFO.value,
                )
            )
        ).scalar_one()
        open_count = (
            await self.session.execute(
                select(func.count(IncidentRecord.id)).where(
                    IncidentRecord.tenant_id == tenant_id, IncidentRecord.status.in_(OPEN_STATUSES)
                )
            )
        ).scalar_one()
        mtti = (
            await self.session.execute(
                select(
                    func.avg(
                        func.extract("epoch", IncidentRecord.isolated_at - IncidentRecord.opened_at)
                    )
                ).where(
                    IncidentRecord.tenant_id == tenant_id,
                    IncidentRecord.isolated_at.is_not(None),
                )
            )
        ).scalar_one_or_none()
        incident_rows = (
            (
                await self.session.execute(
                    select(IncidentRecord)
                    .where(
                        IncidentRecord.tenant_id == tenant_id,
                        IncidentRecord.status.in_(OPEN_STATUSES),
                    )
                    .order_by(IncidentRecord.updated_at.desc())
                    .limit(self.settings.dashboard_incident_limit)
                )
            )
            .scalars()
            .all()
        )
        inventory_rows = (
            await self.session.execute(
                select(
                    InventoryResourceRecord.domain,
                    func.count(InventoryResourceRecord.id),
                    func.avg(InventoryResourceRecord.health),
                )
                .where(InventoryResourceRecord.tenant_id == tenant_id)
                .group_by(InventoryResourceRecord.domain)
            )
        ).all()
        rate_rows = (
            await self.session.execute(
                select(TelemetryEventRecord.domain, func.count(TelemetryEventRecord.id))
                .where(
                    TelemetryEventRecord.tenant_id == tenant_id,
                    TelemetryEventRecord.observed_at >= rate_cutoff,
                )
                .group_by(TelemetryEventRecord.domain)
            )
        ).all()
        rate_seconds = float(self.settings.dashboard_rate_window_seconds)

        return DashboardSnapshot(
            generated_at=now,
            service_health=float(service_health) if service_health is not None else None,
            managed_assets=int(managed_assets),
            active_alarms=int(active_alarms),
            open_incidents=int(open_count),
            mean_time_to_isolate_seconds=float(mtti) if mtti is not None else None,
            incidents=[self._incident_summary(item) for item in incident_rows],
            inventory_by_domain={
                Domain(domain): {
                    "count": int(count),
                    "health": float(health) if health is not None else None,
                }
                for domain, count, health in inventory_rows
            },
            event_rate_by_domain={
                Domain(domain): float(count) / rate_seconds for domain, count in rate_rows
            },
        )

    async def _save_evidence_record(
        self, tenant_id: str, incident_id: UUID | None, evidence: Evidence
    ) -> None:
        payload = evidence.payload
        checksum = hashlib.sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()
        await self.session.execute(
            insert(EvidenceRecord)
            .values(
                id=evidence.id,
                tenant_id=tenant_id,
                incident_id=incident_id,
                kind=evidence.kind,
                source=evidence.source,
                statement=evidence.statement,
                observed_at=evidence.observed_at,
                payload=payload,
                checksum=checksum,
            )
            .on_conflict_do_nothing(index_elements=[EvidenceRecord.id])
        )

    @staticmethod
    def _incident_summary(record: IncidentRecord) -> IncidentSummary:
        return IncidentSummary(
            id=record.id,
            status=IncidentStatus(record.status),
            severity=Severity(record.severity),
            title=record.title,
            summary=record.summary,
            opened_at=record.opened_at,
            updated_at=record.updated_at,
            service_ids=record.service_ids,
            event_count=record.event_count,
            confidence=record.confidence,
            root_cause=record.root_cause,
        )

    @staticmethod
    def _incident_dict(record: IncidentRecord) -> dict[str, Any]:
        return {
            "id": str(record.id),
            "status": record.status,
            "severity": record.severity,
            "title": record.title,
            "summary": record.summary,
            "service_ids": record.service_ids,
            "event_count": record.event_count,
            "root_cause": record.root_cause,
            "confidence": record.confidence,
            "workflow_thread_id": record.workflow_thread_id,
            "opened_at": record.opened_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }

    @staticmethod
    def _remediation_dict(record: RemediationRecord) -> dict[str, Any]:
        return {
            "id": str(record.id),
            "plan": record.plan,
            "plan_hash": record.plan_hash,
            "policy_decision": record.policy_decision,
            "approval": record.approval,
            "status": record.status,
            "results": record.results,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }

    @staticmethod
    def _event_dict(record: TelemetryEventRecord) -> dict[str, Any]:
        return {
            "id": str(record.id),
            "source": record.source,
            "domain": record.domain,
            "event_type": record.event_type,
            "observed_at": record.observed_at.isoformat(),
            "severity": record.severity,
            "resource_id": record.resource_id,
            "service_id": record.service_id,
            "summary": record.summary,
            "attributes": record.attributes,
            "correlation_keys": record.correlation_keys,
            "trace_id": record.trace_id,
        }

    @staticmethod
    def _evidence_dict(record: EvidenceRecord) -> dict[str, Any]:
        return {
            "id": str(record.id),
            "kind": record.kind,
            "source": record.source,
            "statement": record.statement,
            "observed_at": record.observed_at.isoformat(),
            "payload": record.payload,
            "checksum": record.checksum,
        }

    @staticmethod
    def _topology_dict(record: TopologyRelationRecord) -> dict[str, Any]:
        return {
            "source_id": record.source_id,
            "target_id": record.target_id,
            "relation": record.relation,
            "attributes": record.attributes,
            "observed_at": record.observed_at.isoformat(),
        }
