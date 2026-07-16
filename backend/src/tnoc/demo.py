from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
from jsonschema import ValidationError

from tnoc.domain import ApprovalDecision, RemediationPlan, ToolAction
from tnoc.sandbox import SandboxProfile
from tnoc.settings import Settings
from tnoc.tools import ToolExecutor, ToolRegistry, plan_hash


def read_action(
    tool_name: str,
    arguments: dict[str, Any],
    resource_ids: list[str],
) -> ToolAction:
    return ToolAction(
        tool_name=tool_name,
        arguments=arguments,
        target_resource_ids=resource_ids,
        expected_result="deterministic verifier schema passes",
        verification_tool_name=tool_name,
        verification_arguments=arguments,
    )


def demo_settings() -> Settings:
    return cast(
        Settings,
        SimpleNamespace(
            environment="development",
            http_tool_connect_timeout_seconds=3.0,
            http_tool_read_timeout_seconds=10.0,
            max_tool_response_bytes=1_048_576,
        ),
    )


async def replay(
    plan: RemediationPlan,
    *,
    incident_id: str,
    incident_scope: set[str],
    sandbox_profile: SandboxProfile,
) -> dict[str, Any]:
    base_url = os.environ.get("SANDBOX_CONTROLLER_URL", "http://127.0.0.1:8090")
    os.environ["SANDBOX_CONTROLLER_URL"] = base_url
    registry = ToolRegistry(
        Path("config/tools.sandbox.json"),
        Path("config/policy.json"),
    )
    executor = ToolExecutor(demo_settings(), registry)
    certificate_hash = plan_hash(plan)
    policy = registry.evaluate(plan, incident_scope)
    if not policy.allowed or not policy.requires_approval:
        raise RuntimeError("Gemini plan did not pass deterministic policy")
    if len(plan.actions) != 1:
        raise RuntimeError("Sandbox proof requires exactly one bounded action")
    action = plan.actions[0]
    if not all(
        (
            action.rollback_tool_name,
            action.rollback_arguments,
            action.rollback_verification_tool_name,
            action.rollback_verification_arguments,
        )
    ):
        raise RuntimeError("Gemini plan must include complete rollback and rollback verification")
    approval = ApprovalDecision(
        approved=True,
        actor="demo-operator",
        plan_hash=certificate_hash,
        reason="Approved for Gemini-generated sandbox plan",
        decided_at=datetime.now(UTC),
    )

    async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
        reset = await client.post("/reset", json=sandbox_profile.model_dump(mode="json"))
        reset.raise_for_status()
        baseline_state = reset.json()

    tampered = plan.model_copy(deep=True)
    tampered.summary = f"{tampered.summary} [modified after approval]"
    tamper_rejected = False
    try:
        await executor.execute(
            action=tampered.actions[0],
            tenant_id="sandbox-tenant",
            incident_id=incident_id,
            expected_plan_hash=plan_hash(tampered),
            approval=approval,
            sequence=1,
        )
    except PermissionError:
        tamper_rejected = True

    excessive_shift_blocked = "shift_percent" not in action.arguments
    if "shift_percent" in action.arguments:
        excessive = plan.model_copy(deep=True)
        excessive.actions[0].arguments["shift_percent"] = 60
        try:
            registry.evaluate(excessive, incident_scope)
        except ValidationError:
            excessive_shift_blocked = True

    applied = await executor.execute(
        action=action,
        tenant_id="sandbox-tenant",
        incident_id=incident_id,
        expected_plan_hash=certificate_hash,
        approval=approval,
        sequence=1,
    )
    duplicate = await executor.execute(
        action=action,
        tenant_id="sandbox-tenant",
        incident_id=incident_id,
        expected_plan_hash=certificate_hash,
        approval=approval,
        sequence=1,
    )
    verification = await executor.execute(
        action=read_action(
            action.verification_tool_name,
            action.verification_arguments,
            action.target_resource_ids,
        ),
        tenant_id="sandbox-tenant",
        incident_id=incident_id,
        expected_plan_hash=certificate_hash,
        approval=approval,
        sequence=2,
    )
    rollback = await executor.execute(
        action=ToolAction(
            tool_name=cast(str, action.rollback_tool_name),
            arguments=cast(dict[str, Any], action.rollback_arguments),
            target_resource_ids=action.target_resource_ids,
            expected_result="rollback accepted",
            verification_tool_name=action.verification_tool_name,
            verification_arguments=action.verification_arguments,
        ),
        tenant_id="sandbox-tenant",
        incident_id=incident_id,
        expected_plan_hash=certificate_hash,
        approval=approval,
        sequence=3,
    )
    restored = await executor.execute(
        action=read_action(
            cast(str, action.rollback_verification_tool_name),
            cast(dict[str, Any], action.rollback_verification_arguments),
            action.target_resource_ids,
        ),
        tenant_id="sandbox-tenant",
        incident_id=incident_id,
        expected_plan_hash=certificate_hash,
        approval=approval,
        sequence=4,
    )
    async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
        final_state_response = await client.get("/state")
        final_state_response.raise_for_status()
        final_state = final_state_response.json()

    proof_passed = all(
        [
            tamper_rejected,
            excessive_shift_blocked,
            applied.ok,
            duplicate.ok and duplicate.output.get("duplicate_suppressed") is True,
            not verification.ok,
            rollback.ok,
            restored.ok and restored.output.get("restoration_verified") is True,
            final_state.get("apply_count") == 1,
            final_state.get("rollback_count") == 1,
        ]
    )
    return {
        "scenario": incident_id,
        "sandbox": True,
        "proof_passed": proof_passed,
        "plan_hash": certificate_hash,
        "plan": plan.model_dump(mode="json"),
        "policy": policy.model_dump(mode="json"),
        "adversarial_proofs": {
            "tampered_approval_rejected": tamper_rejected,
            "excessive_60_percent_shift_blocked": excessive_shift_blocked,
            "duplicate_delivery_suppressed": duplicate.output.get("duplicate_suppressed"),
        },
        "execution": {
            "change_applied": applied.ok,
            "post_change_verification_passed": verification.ok,
            "post_change_verification_error": verification.error,
            "rollback_applied": rollback.ok,
            "rollback_independently_verified": restored.ok,
            "baseline_metrics": baseline_state.get("metrics", {}),
            "post_change_metrics": verification.output.get("metrics", {}),
            "restored_metrics": restored.output.get("metrics", {}),
        },
        "final_state": final_state,
    }


def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--incident-id", required=True)
    parser.add_argument("--resource-id", action="append", required=True)
    parser.add_argument("--sandbox-profile", type=Path, required=True)
    arguments = parser.parse_args()
    plan = RemediationPlan.model_validate_json(arguments.plan.read_text(encoding="utf-8"))
    sandbox_profile = SandboxProfile.model_validate_json(
        arguments.sandbox_profile.read_text(encoding="utf-8")
    )
    report = asyncio.run(
        replay(
            plan,
            incident_id=arguments.incident_id,
            incident_scope=set(arguments.resource_id),
            sandbox_profile=sandbox_profile,
        )
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["proof_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
