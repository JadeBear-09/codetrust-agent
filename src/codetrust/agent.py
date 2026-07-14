from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from codetrust.diff_parser import parse_unified_diff
from codetrust.impact import map_impact
from codetrust.llm import synthesize
from codetrust.models import AgentEvent, Severity, Verdict, VerificationReport
from codetrust.rules import risk_score, run_rules
from codetrust.testgen import generate_adversarial_tests


def verify_change(
    ticket: str,
    diff: str,
    *,
    offline: bool = False,
    source: dict[str, str] | None = None,
) -> VerificationReport:
    timeline: list[AgentEvent] = []

    files = parse_unified_diff(diff)
    timeline.append(AgentEvent("scope", "complete", f"Mapped {len(files)} changed file(s)."))

    impact_areas = map_impact(files)
    timeline.append(
        AgentEvent(
            "impact-map",
            "complete",
            f"Identified {len(impact_areas)} affected domain(s).",
        )
    )

    findings, checks = run_rules(files)
    timeline.append(
        AgentEvent(
            "challenge",
            "complete",
            f"Ran {len(checks)} targeted gate(s); produced {len(findings)} finding(s).",
        )
    )

    synthesis = synthesize(ticket, diff, findings, offline)
    timeline.append(
        AgentEvent(
            "reconstruct-intent",
            "complete",
            "Used model synthesis."
            if synthesis.model
            else "Used deterministic offline reconstruction.",
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

    score = risk_score(findings)
    verdict = _verdict(findings, score)
    timeline.append(
        AgentEvent("decision", "complete", f"Verdict {verdict.value}; score {score}/100.")
    )

    created_at = datetime.now(UTC).isoformat()
    run_id = f"ct-{uuid.uuid4().hex[:10]}"
    evidence_payload = json.dumps(
        {"ticket": ticket, "diff": diff, "findings": [item.to_dict() for item in findings]},
        sort_keys=True,
    )
    evidence_hash = hashlib.sha256(evidence_payload.encode()).hexdigest()

    return VerificationReport(
        run_id=run_id,
        created_at=created_at,
        intent=synthesis.intent,
        verdict=verdict,
        risk_score=score,
        summary=synthesis.summary,
        files_changed=len(files),
        findings=findings,
        checks=checks,
        unresolved_questions=synthesis.unresolved_questions,
        timeline=timeline,
        impact_areas=impact_areas,
        adversarial_tests=adversarial_tests,
        source=source or {"type": "diff"},
        model_used=synthesis.model,
        evidence_hash=evidence_hash,
    )


def _verdict(findings, score: int) -> Verdict:
    if any(item.severity is Severity.CRITICAL for item in findings) or score >= 70:
        return Verdict.BLOCK
    if any(item.severity is Severity.HIGH for item in findings) or score >= 35:
        return Verdict.NEEDS_REVIEW
    return Verdict.PASS
