from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from codetrust.diff_parser import parse_unified_diff
from codetrust.impact import map_impact
from codetrust.llm import synthesize
from codetrust.models import (
    AgentEvent,
    InterpretationClaim,
    ScopeComparison,
    Severity,
    SynthesisStatus,
    Verdict,
    VerificationReport,
)
from codetrust.rules import risk_score, run_rules
from codetrust.scope import analyze_scope
from codetrust.testgen import generate_adversarial_tests


def verify_change(
    ticket: str,
    diff: str,
    *,
    offline: bool = False,
    source: dict[str, str] | None = None,
    interpretations: list[InterpretationClaim] | None = None,
    change_claim: str = "",
    additional_questions: list[str] | None = None,
    scope_comparison: ScopeComparison | None = None,
) -> VerificationReport:
    started = time.monotonic()
    timeline: list[AgentEvent] = []

    files = parse_unified_diff(diff)
    timeline.append(AgentEvent("scope", "complete", f"Mapped {len(files)} changed file(s)."))

    scope_trust = (source or {}).get("intent_trust", "trusted")
    provenance_detail = {
        "trusted": "Used explicit scope supplied by user.",
        "inferred": "Used INFERRED scope anchored only to base-repository evidence.",
        "insufficient": "Base-repository evidence was insufficient; review floor applied.",
    }.get(scope_trust, f"Used scope trust state: {scope_trust}.")
    timeline.append(AgentEvent("scope-provenance", "complete", provenance_detail))

    impact_areas = map_impact(files)
    timeline.append(
        AgentEvent(
            "impact-map",
            "complete",
            f"Identified {len(impact_areas)} affected domain(s).",
        )
    )

    scope = analyze_scope(ticket, files, interpretations, scope_trust)
    timeline.append(
        AgentEvent(
            "scope-alignment",
            "complete",
            f"Mapped {len(scope.alignments)} intent-to-change relationship(s).",
        )
    )

    technical_findings, applicable_checks, skipped_checks = run_rules(files)
    findings = [*scope.findings, *technical_findings]
    checks = ["scope-alignment", *applicable_checks]
    timeline.append(
        AgentEvent(
            "challenge",
            "complete",
            (
                f"Ran {len(applicable_checks)} applicable gate(s); "
                f"skipped {len(skipped_checks)}; produced {len(findings)} finding(s)."
            ),
        )
    )

    synthesis = synthesize(
        ticket,
        diff,
        findings,
        offline,
        change_claim=change_claim,
        scope_trust=scope_trust,
    )
    timeline.append(
        AgentEvent(
            "reconstruct-intent",
            "complete",
            "Used model synthesis." if synthesis.model else "Model synthesis explicitly disabled.",
        )
    )

    adversarial_tests = generate_adversarial_tests(findings)
    timeline.append(
        AgentEvent(
            "test-design",
            "complete",
            f"Generated {len(adversarial_tests)} adversarial test(s).",
        )
    )

    score = risk_score(
        [item for item in findings if "-INFERRED-" not in item.rule_id]
    )
    intent_is_structured = any(
        (
            scope.snapshot.outcome,
            scope.snapshot.in_scope,
            scope.snapshot.out_of_scope,
            scope.snapshot.acceptance_criteria,
        )
    )
    verdict = _verdict(
        findings,
        score,
        intent_is_structured,
        applicable_checks,
        scope_trust,
        scope_comparison,
    )
    timeline.append(
        AgentEvent("decision", "complete", f"Verdict {verdict.value}; score {score}/100.")
    )

    created_at = datetime.now(UTC).isoformat()
    run_id = f"ct-{uuid.uuid4().hex[:10]}"
    unresolved_questions = list(
        dict.fromkeys(
            [
                *scope.questions,
                *synthesis.unresolved_questions,
                *(additional_questions or []),
            ]
        )
    )
    evidence_payload = json.dumps(
        {
            "ticket": ticket,
            "change_claim": change_claim,
            "diff": diff,
            "findings": [item.to_dict() for item in findings],
            "source": source or {"type": "diff"},
            "scope_comparison": asdict(scope_comparison) if scope_comparison else None,
            "intent_snapshot": {
                "outcome": scope.snapshot.outcome,
                "in_scope": scope.snapshot.in_scope,
                "out_of_scope": scope.snapshot.out_of_scope,
                "acceptance_criteria": scope.snapshot.acceptance_criteria,
            },
            "interpretations": [
                {"role": item.role, "text": item.text, "source": item.source}
                for item in interpretations or []
            ],
            "model_used": synthesis.model,
            "synthesis_status": synthesis.status,
            "synthesis_attempts": synthesis.attempts,
            "synthesis_duration_ms": synthesis.duration_ms,
            "synthesis_input_truncated": synthesis.input_truncated,
            "applicable_checks": applicable_checks,
            "skipped_checks": skipped_checks,
        },
        sort_keys=True,
    )
    evidence_hash = hashlib.sha256(evidence_payload.encode()).hexdigest()

    report_intent = synthesis.intent
    report_summary = synthesis.summary
    if scope_trust == "insufficient":
        report_intent = "Repository scope not established"
        report_summary = (
            "Base-repository evidence could not establish reliable scope; human review required."
        )

    return VerificationReport(
        run_id=run_id,
        created_at=created_at,
        intent=report_intent,
        verdict=verdict,
        risk_score=score,
        summary=report_summary,
        files_changed=len(files),
        findings=findings,
        checks=checks,
        unresolved_questions=unresolved_questions,
        timeline=timeline,
        impact_areas=impact_areas,
        adversarial_tests=adversarial_tests,
        source=source or {"type": "diff"},
        model_used=synthesis.model,
        synthesis_status=SynthesisStatus(synthesis.status),
        synthesis_attempts=synthesis.attempts,
        synthesis_duration_ms=synthesis.duration_ms,
        synthesis_input_truncated=synthesis.input_truncated,
        duration_ms=round((time.monotonic() - started) * 1000),
        evidence_hash=evidence_hash,
        intent_snapshot=scope.snapshot,
        interpretations=interpretations or [],
        alignments=scope.alignments,
        scope_coverage=scope.coverage,
        scope_drift=scope.drift,
        applicable_checks=applicable_checks,
        skipped_checks=skipped_checks,
        gate_coverage=(
            round(len(applicable_checks) / (len(applicable_checks) + len(skipped_checks)) * 100)
            if applicable_checks or skipped_checks
            else 0
        ),
        scope_comparison=scope_comparison,
    )


def _verdict(
    findings,
    score: int,
    intent_is_structured: bool,
    applicable_checks: list[str],
    scope_trust: str = "trusted",
    scope_comparison: ScopeComparison | None = None,
) -> Verdict:
    if any(item.rule_id == "CT-SCOPE-001" for item in findings):
        return Verdict.BLOCK
    if any(item.severity is Severity.CRITICAL for item in findings) or score >= 70:
        return Verdict.BLOCK
    if any(item.severity in {Severity.HIGH, Severity.MEDIUM} for item in findings) or score >= 35:
        return Verdict.NEEDS_REVIEW
    if scope_trust == "insufficient":
        return Verdict.NEEDS_REVIEW
    if scope_comparison and (
        scope_comparison.relationship == "divergent"
        or (scope_comparison.distance is not None and scope_comparison.distance >= 60)
    ):
        return Verdict.NEEDS_REVIEW
    if not intent_is_structured or not applicable_checks:
        return Verdict.NEEDS_REVIEW
    return Verdict.PASS
