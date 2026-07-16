from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

SourceName = Literal["telemetry", "topology", "change_history", "security"]
RootCauseCode = Literal[
    "policy_regression",
    "capacity_congestion",
    "credential_attack",
    "insufficient_evidence",
]
SOURCE_NAMES: tuple[SourceName, ...] = (
    "telemetry",
    "topology",
    "change_history",
    "security",
)
DEFAULT_EXPECTATIONS_PATH = Path("evals/intelligence_expectations.json")


class ProofEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{2,127}$")
    source: SourceName
    statement: str = Field(min_length=1, max_length=4096)
    attributes: dict[str, Any] = Field(default_factory=dict)


class ProofSources(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telemetry: list[ProofEvidence]
    topology: list[ProofEvidence]
    change_history: list[ProofEvidence]
    security: list[ProofEvidence]

    def for_source(self, source: SourceName) -> list[ProofEvidence]:
        return cast(list[ProofEvidence], getattr(self, source))


class IncidentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,127}$")
    title: str
    description: str = Field(min_length=1, max_length=4096)
    submitted_by: str = Field(min_length=1, max_length=256)
    submitted_at: datetime
    domain: str = Field(min_length=1, max_length=128)
    resource_ids: list[str] = Field(min_length=1, max_length=100)
    sources: ProofSources


class IntelligenceExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,127}$")
    expected_root_cause_code: RootCauseCode
    expected_safe_to_plan: bool


class IntelligenceCase(IncidentInput):
    expected_root_cause_code: RootCauseCode
    expected_safe_to_plan: bool


class SourceFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    specialist: SourceName
    candidate_codes: list[RootCauseCode]
    evidence_ids: list[str]
    summary: str
    confidence: float = Field(ge=0, le=1)
    uncertainty: list[str]


class IntelligenceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_cause_code: RootCauseCode
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]
    reasoning_summary: str
    uncertainty: list[str]
    safe_to_plan: bool

    @model_validator(mode="after")
    def require_evidence_for_planning(self) -> IntelligenceDecision:
        if self.safe_to_plan and not self.evidence_ids:
            raise ValueError("Planning decision requires evidence")
        return self


def load_incident_inputs(path: Path) -> list[IncidentInput]:
    if path.is_dir():
        documents = [
            json.loads(document.read_text(encoding="utf-8"))
            for document in sorted(path.glob("*.json"))
        ]
    elif path.suffix == ".jsonl":
        documents = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        documents = payload if isinstance(payload, list) else [payload]
    incidents = [IncidentInput.model_validate(document) for document in documents]
    if not incidents:
        raise ValueError(f"No incident JSON documents found at {path}")
    ids = [incident.id for incident in incidents]
    if len(set(ids)) != len(ids):
        raise ValueError("Incident IDs must be unique")
    return incidents


def load_intelligence_cases(
    path: Path,
    expectations_path: Path = DEFAULT_EXPECTATIONS_PATH,
) -> list[IntelligenceCase]:
    incidents = load_incident_inputs(path)
    expectation_payload = json.loads(expectations_path.read_text(encoding="utf-8"))
    expectations = {
        item.incident_id: item
        for item in (
            IntelligenceExpectation.model_validate(document) for document in expectation_payload
        )
    }
    missing = [incident.id for incident in incidents if incident.id not in expectations]
    if missing:
        raise ValueError(f"Missing evaluation expectations for: {', '.join(missing)}")
    return [
        IntelligenceCase.model_validate(
            {
                **incident.model_dump(mode="json"),
                "expected_root_cause_code": expectations[incident.id].expected_root_cause_code,
                "expected_safe_to_plan": expectations[incident.id].expected_safe_to_plan,
            }
        )
        for incident in incidents
    ]
