from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Verdict(StrEnum):
    BLOCK = "BLOCK"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    PASS = "PASS"


class AlignmentStatus(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class ChangedLine:
    path: str
    line: int
    text: str
    kind: str


@dataclass(frozen=True)
class ChangedFile:
    path: str
    added: tuple[ChangedLine, ...] = ()
    removed: tuple[ChangedLine, ...] = ()

    @property
    def added_text(self) -> str:
        return "\n".join(line.text for line in self.added)

    @property
    def removed_text(self) -> str:
        return "\n".join(line.text for line in self.removed)


@dataclass(frozen=True)
class Finding:
    rule_id: str
    title: str
    severity: Severity
    confidence: float
    path: str
    line: int
    evidence: str
    impact: str
    challenge: str
    suggested_test: str
    human_question: str = ""
    ticket_evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data


@dataclass
class AgentEvent:
    step: str
    status: str
    detail: str


@dataclass(frozen=True)
class ImpactArea:
    name: str
    kind: str
    risk: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class AdversarialTest:
    rule_id: str
    name: str
    rationale: str
    code: str


@dataclass(frozen=True)
class IntentSnapshot:
    outcome: tuple[str, ...] = ()
    in_scope: tuple[str, ...] = ()
    out_of_scope: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()


@dataclass(frozen=True)
class InterpretationClaim:
    role: str
    text: str
    source: str = ""


@dataclass(frozen=True)
class ScopeAlignment:
    status: AlignmentStatus
    clause: str
    path: str
    line: int
    change_evidence: str
    rationale: str
    actor: str = "code"


@dataclass
class VerificationReport:
    run_id: str
    created_at: str
    intent: str
    verdict: Verdict
    risk_score: int
    summary: str
    files_changed: int
    findings: list[Finding] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    timeline: list[AgentEvent] = field(default_factory=list)
    impact_areas: list[ImpactArea] = field(default_factory=list)
    adversarial_tests: list[AdversarialTest] = field(default_factory=list)
    source: dict[str, str] = field(default_factory=dict)
    model_used: str | None = None
    evidence_hash: str = ""
    intent_snapshot: IntentSnapshot | None = None
    interpretations: list[InterpretationClaim] = field(default_factory=list)
    alignments: list[ScopeAlignment] = field(default_factory=list)
    scope_coverage: int | None = None
    scope_drift: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "intent": self.intent,
            "verdict": self.verdict.value,
            "risk_score": self.risk_score,
            "summary": self.summary,
            "files_changed": self.files_changed,
            "findings": [finding.to_dict() for finding in self.findings],
            "checks": self.checks,
            "unresolved_questions": self.unresolved_questions,
            "timeline": [asdict(event) for event in self.timeline],
            "impact_areas": [asdict(area) for area in self.impact_areas],
            "adversarial_tests": [asdict(test) for test in self.adversarial_tests],
            "source": self.source,
            "model_used": self.model_used,
            "evidence_hash": self.evidence_hash,
            "intent_snapshot": asdict(self.intent_snapshot) if self.intent_snapshot else None,
            "interpretations": [asdict(item) for item in self.interpretations],
            "alignments": [
                {**asdict(item), "status": item.status.value} for item in self.alignments
            ],
            "scope_coverage": self.scope_coverage,
            "scope_drift": self.scope_drift,
        }
