from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Domain(StrEnum):
    RAN = "ran"
    TRANSPORT = "transport"
    CORE = "core"
    DNS = "dns"
    CLOUD = "cloud"
    SECURITY = "security"
    BSS = "bss"
    OSS = "oss"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    DIAGNOSED = "diagnosed"
    AWAITING_APPROVAL = "awaiting_approval"
    DECISION_SUBMITTED = "decision_submitted"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    FAILED = "failed"


class SideEffect(StrEnum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class TelemetryEvent(BaseModel):
    """Normalized CloudEvents-compatible observation. Payload remains untrusted data."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    tenant_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=512)
    domain: Domain
    event_type: str = Field(min_length=1, max_length=256)
    observed_at: datetime
    severity: Severity
    resource_id: str = Field(min_length=1, max_length=512)
    service_id: str | None = Field(default=None, max_length=512)
    summary: str = Field(min_length=1, max_length=2048)
    attributes: dict[str, Any] = Field(default_factory=dict)
    correlation_keys: dict[str, str] = Field(default_factory=dict)
    trace_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def require_timezone(self) -> TelemetryEvent:
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must include timezone")
        return self


class InventoryResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=128)
    domain: Domain
    kind: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=512)
    site_id: str | None = Field(default=None, max_length=256)
    service_ids: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    health: float | None = Field(default=None, ge=0, le=1)
    observed_at: datetime

    @model_validator(mode="after")
    def require_timezone(self) -> InventoryResource:
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must include timezone")
        return self


class TopologyRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=512)
    target_id: str = Field(min_length=1, max_length=512)
    relation: str = Field(min_length=1, max_length=128)
    attributes: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime

    @model_validator(mode="after")
    def require_timezone(self) -> TopologyRelation:
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must include timezone")
        return self


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    kind: str
    source: str
    statement: str
    observed_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    checksum: str | None = None


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cause: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[UUID]
    contradictions: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class SpecialistFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    specialist: str
    hypotheses: list[Hypothesis]
    observations: list[str]
    uncertainty: list[str]


class RootCauseDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_cause: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[UUID]
    rejected_hypotheses: list[str]
    uncertainty: list[str]
    safe_to_plan: bool

    @model_validator(mode="after")
    def require_evidence_for_action(self) -> RootCauseDecision:
        if self.safe_to_plan and not self.evidence_ids:
            raise ValueError("A decision cannot be safe to plan without evidence")
        return self


class ToolAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: dict[str, Any]
    target_resource_ids: list[str] = Field(min_length=1)
    expected_result: str
    verification_tool_name: str
    verification_arguments: dict[str, Any]
    rollback_tool_name: str | None = None
    rollback_arguments: dict[str, Any] | None = None
    rollback_verification_tool_name: str | None = None
    rollback_verification_arguments: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_complete_rollback(self) -> ToolAction:
        rollback_fields = (
            self.rollback_arguments,
            self.rollback_verification_tool_name,
            self.rollback_verification_arguments,
        )
        if self.rollback_tool_name and any(value is None for value in rollback_fields):
            raise ValueError(
                "Rollback tool, arguments, verifier, and verifier arguments are atomic"
            )
        if not self.rollback_tool_name and any(value is not None for value in rollback_fields):
            raise ValueError("Rollback fields require rollback_tool_name")
        return self


class RemediationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    risk: Literal["low", "medium", "high", "critical"]
    actions: list[ToolAction] = Field(min_length=1)
    blast_radius: list[str] = Field(min_length=1)
    preconditions: list[str] = Field(min_length=1)
    stop_conditions: list[str] = Field(min_length=1)
    requires_approval: bool


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    requires_approval: bool
    reasons: list[str]
    blocked_actions: list[str]


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    actor: str
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=4096)
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    idempotency_key: str
    ok: bool
    status_code: int | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime
    finished_at: datetime


class IncidentSummary(BaseModel):
    id: UUID
    status: IncidentStatus
    severity: Severity
    title: str
    summary: str
    opened_at: datetime
    updated_at: datetime
    service_ids: list[str]
    event_count: int
    confidence: float | None
    root_cause: str | None


class DashboardSnapshot(BaseModel):
    generated_at: datetime
    service_health: float | None
    managed_assets: int
    active_alarms: int
    open_incidents: int
    mean_time_to_isolate_seconds: float | None
    incidents: list[IncidentSummary]
    inventory_by_domain: dict[Domain, dict[str, float | int | None]]
    event_rate_by_domain: dict[Domain, float]
