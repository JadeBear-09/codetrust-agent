"""Initial ChangeGuard evidence and control-plane schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = (
    "telemetry_events",
    "inventory_resources",
    "topology_relations",
    "incidents",
    "incident_events",
    "evidence",
    "remediations",
    "knowledge_documents",
    "audit_log",
    "audit_heads",
    "outbox",
)


def upgrade() -> None:
    op.create_table(
        "telemetry_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("source", sa.String(512), nullable=False),
        sa.Column("domain", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(256), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(512), nullable=False),
        sa.Column("service_id", sa.String(512)),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column("correlation_keys", postgresql.JSONB(), nullable=False),
        sa.Column("trace_id", sa.String(128)),
    )
    _indexes(
        "telemetry_events",
        {
            "ix_telemetry_events_tenant_id": ("tenant_id",),
            "ix_telemetry_events_domain": ("domain",),
            "ix_telemetry_events_observed_at": ("observed_at",),
            "ix_telemetry_events_severity": ("severity",),
            "ix_telemetry_events_resource_id": ("resource_id",),
            "ix_telemetry_events_service_id": ("service_id",),
            "ix_telemetry_events_trace_id": ("trace_id",),
            "ix_telemetry_tenant_observed": ("tenant_id", "observed_at"),
            "ix_telemetry_tenant_service": ("tenant_id", "service_id"),
        },
    )

    op.create_table(
        "inventory_resources",
        sa.Column("id", sa.String(512), primary_key=True),
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("domain", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(128), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("site_id", sa.String(256)),
        sa.Column("service_ids", postgresql.JSONB(), nullable=False),
        sa.Column("labels", postgresql.JSONB(), nullable=False),
        sa.Column("health", sa.Float()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    _indexes(
        "inventory_resources",
        {
            "ix_inventory_resources_domain": ("domain",),
            "ix_inventory_resources_site_id": ("site_id",),
            "ix_inventory_tenant_domain": ("tenant_id", "domain"),
        },
    )

    op.create_table(
        "topology_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("source_id", sa.String(512), nullable=False),
        sa.Column("target_id", sa.String(512), nullable=False),
        sa.Column("relation", sa.String(128), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "source_id", "target_id", "relation", name="uq_topology_relation"
        ),
    )
    _indexes(
        "topology_relations",
        {
            "ix_topology_relations_tenant_id": ("tenant_id",),
            "ix_topology_relations_source_id": ("source_id",),
            "ix_topology_relations_target_id": ("target_id",),
            "ix_topology_tenant_source": ("tenant_id", "source_id"),
            "ix_topology_tenant_target": ("tenant_id", "target_id"),
        },
    )

    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("correlation_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("service_ids", postgresql.JSONB(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("root_cause", sa.Text()),
        sa.Column("confidence", sa.Float()),
        sa.Column("workflow_thread_id", sa.String(128), unique=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("isolated_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    _indexes(
        "incidents",
        {
            "ix_incidents_tenant_id": ("tenant_id",),
            "ix_incidents_correlation_fingerprint": ("correlation_fingerprint",),
            "ix_incidents_status": ("status",),
            "ix_incidents_severity": ("severity",),
            "ix_incident_tenant_status_updated": ("tenant_id", "status", "updated_at"),
        },
    )

    op.create_table(
        "incident_events",
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("telemetry_events.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("ix_incident_events_tenant_id", "incident_events", ["tenant_id"])

    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
        ),
        sa.Column("kind", sa.String(128), nullable=False),
        sa.Column("source", sa.String(512), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
    )
    _indexes(
        "evidence",
        {
            "ix_evidence_tenant_id": ("tenant_id",),
            "ix_evidence_incident_id": ("incident_id",),
        },
    )

    op.create_table(
        "remediations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plan", postgresql.JSONB(), nullable=False),
        sa.Column("plan_hash", sa.String(64), nullable=False),
        sa.Column("policy_decision", postgresql.JSONB(), nullable=False),
        sa.Column("approval", postgresql.JSONB()),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("results", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "incident_id", "plan_hash", name="uq_remediation_plan"),
    )
    _indexes(
        "remediations",
        {
            "ix_remediations_tenant_id": ("tenant_id",),
            "ix_remediations_incident_id": ("incident_id",),
        },
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("source_uri", sa.String(2048), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "content_sha256", name="uq_knowledge_tenant_hash"),
    )
    op.create_index("ix_knowledge_documents_tenant_id", "knowledge_documents", ["tenant_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="SET NULL"),
        ),
        sa.Column("event_type", sa.String(256), nullable=False),
        sa.Column("actor", sa.String(512), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("previous_hash", sa.String(64)),
        sa.Column("record_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    _indexes(
        "audit_log",
        {"ix_audit_log_tenant_id": ("tenant_id",), "ix_audit_log_incident_id": ("incident_id",)},
    )

    op.create_table(
        "audit_heads",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("record_hash", sa.String(64)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("topic", sa.String(256), nullable=False),
        sa.Column("message_key", sa.String(512), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(256)),
    )
    _indexes(
        "outbox",
        {
            "ix_outbox_tenant_id": ("tenant_id",),
            "ix_outbox_topic": ("topic",),
            "ix_outbox_published_at": ("published_at",),
            "ix_outbox_unpublished": ("published_at", "created_at"),
        },
    )

    for table in TENANT_TABLES:
        predicate = "tenant_id = current_setting('app.tenant_id', true)"
        op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        op.execute(
            sa.text(
                f'CREATE POLICY tenant_isolation ON "{table}" '
                f"USING ({predicate}) WITH CHECK ({predicate})"
            )
        )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
    for table in reversed(TENANT_TABLES):
        op.drop_table(table)


def _indexes(table: str, definitions: dict[str, tuple[str, ...]]) -> None:
    for name, columns in definitions.items():
        op.create_index(name, table, list(columns))
