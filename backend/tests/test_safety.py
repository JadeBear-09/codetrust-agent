from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tnoc.domain import (
    ApprovalDecision,
    RemediationPlan,
    RootCauseDecision,
    ToolAction,
)
from tnoc.settings import Settings
from tnoc.tools import ToolExecutor, ToolRegistry, plan_hash

EXAMPLE_ENV = Path(__file__).parents[1] / ".env.example"


def _write_documents(tmp_path: Path, verifier_has_schema: bool = True) -> tuple[Path, Path]:
    verifier_schema = (
        {
            "type": "object",
            "properties": {"state": {"const": "healthy"}},
            "required": ["state"],
            "additionalProperties": False,
        }
        if verifier_has_schema
        else None
    )
    catalog = {
        "version": 1,
        "tools": [
            {
                "name": "controller.change",
                "description": "Apply a bounded controller change",
                "method": "POST",
                "base_url_env": "CONTROLLER_URL",
                "path": "/changes",
                "side_effect": "write",
                "requires_approval": True,
                "target_argument_fields": ["resource_id"],
                "request_schema": {
                    "type": "object",
                    "properties": {"resource_id": {"type": "string"}},
                    "required": ["resource_id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "controller.rollback",
                "description": "Restore the prior controller state",
                "method": "POST",
                "base_url_env": "CONTROLLER_URL",
                "path": "/rollbacks",
                "side_effect": "write",
                "requires_approval": True,
                "target_argument_fields": ["resource_id"],
                "request_schema": {
                    "type": "object",
                    "properties": {"resource_id": {"type": "string"}},
                    "required": ["resource_id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "verify.state",
                "description": "Read the intended state",
                "method": "GET",
                "base_url_env": "CONTROLLER_URL",
                "path": "/state",
                "side_effect": "read",
                "requires_approval": False,
                "target_argument_fields": ["resource_id"],
                "request_schema": {
                    "type": "object",
                    "properties": {"resource_id": {"type": "string"}},
                    "required": ["resource_id"],
                    "additionalProperties": False,
                },
                "response_schema": verifier_schema,
            },
            {
                "name": "verify.rollback",
                "description": "Read the restored state",
                "method": "GET",
                "base_url_env": "CONTROLLER_URL",
                "path": "/rollback-state",
                "side_effect": "read",
                "requires_approval": False,
                "target_argument_fields": ["resource_id"],
                "request_schema": {
                    "type": "object",
                    "properties": {"resource_id": {"type": "string"}},
                    "required": ["resource_id"],
                    "additionalProperties": False,
                },
                "response_schema": {
                    "type": "object",
                    "properties": {"state": {"const": "restored"}},
                    "required": ["state"],
                    "additionalProperties": False,
                },
            },
        ],
    }
    policy = {
        "version": 1,
        "default_write_policy": "require_approval",
        "default_destructive_policy": "deny",
        "required_plan_fields": ["blast_radius", "preconditions", "stop_conditions"],
        "auto_approve_tools": [],
        "denied_tools": [],
    }
    catalog_path = tmp_path / "tools.json"
    policy_path = tmp_path / "policy.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    return catalog_path, policy_path


def _action(tool_name: str = "controller.change") -> ToolAction:
    arguments = {"resource_id": "resource-1"}
    return ToolAction(
        tool_name=tool_name,
        arguments=arguments,
        target_resource_ids=["resource-1"],
        expected_result="healthy",
        verification_tool_name="verify.state",
        verification_arguments=arguments,
        rollback_tool_name="controller.rollback",
        rollback_arguments=arguments,
        rollback_verification_tool_name="verify.rollback",
        rollback_verification_arguments=arguments,
    )


def _plan(action: ToolAction | None = None) -> RemediationPlan:
    return RemediationPlan(
        summary="Bounded change",
        risk="medium",
        actions=[action or _action()],
        blast_radius=["resource-1"],
        preconditions=["current state captured"],
        stop_conditions=["verification fails"],
        requires_approval=True,
    )


@pytest.mark.parametrize("risk", ["low", "medium", "high"])
def test_write_plan_requires_exact_approval_and_rollback(tmp_path: Path, risk: str) -> None:
    catalog, policy = _write_documents(tmp_path)
    registry = ToolRegistry(catalog, policy)
    plan = _plan()
    plan.risk = cast(Any, risk)
    decision = registry.evaluate(plan, {"resource-1"})
    assert decision.allowed
    assert decision.requires_approval
    assert decision.blocked_actions == []


def test_unknown_tool_is_fail_closed(tmp_path: Path) -> None:
    catalog, policy = _write_documents(tmp_path)
    registry = ToolRegistry(catalog, policy)
    decision = registry.evaluate(_plan(_action("controller.not-allowlisted")), {"resource-1"})
    assert not decision.allowed
    assert "controller.not-allowlisted" in decision.blocked_actions


def test_verifier_without_deterministic_schema_is_blocked(tmp_path: Path) -> None:
    catalog, policy = _write_documents(tmp_path, verifier_has_schema=False)
    decision = ToolRegistry(catalog, policy).evaluate(_plan(), {"resource-1"})
    assert not decision.allowed
    assert "verify.state" in decision.blocked_actions


def test_verifier_without_target_binding_is_blocked(tmp_path: Path) -> None:
    catalog, policy = _write_documents(tmp_path)
    document = json.loads(catalog.read_text(encoding="utf-8"))
    verifier = next(tool for tool in document["tools"] if tool["name"] == "verify.state")
    verifier["target_argument_fields"] = []
    catalog.write_text(json.dumps(document), encoding="utf-8")
    decision = ToolRegistry(catalog, policy).evaluate(_plan(), {"resource-1"})
    assert not decision.allowed
    assert "verify.state" in decision.blocked_actions


def test_partial_rollback_contract_is_invalid() -> None:
    with pytest.raises(ValidationError):
        ToolAction(
            tool_name="controller.change",
            arguments={},
            target_resource_ids=["resource-1"],
            expected_result="healthy",
            verification_tool_name="verify.state",
            verification_arguments={},
            rollback_tool_name="controller.rollback",
            rollback_arguments={},
        )


def test_empty_plan_is_invalid() -> None:
    with pytest.raises(ValidationError):
        RemediationPlan(
            summary="No-op",
            risk="low",
            actions=[],
            blast_radius=[],
            preconditions=[],
            stop_conditions=[],
            requires_approval=False,
        )


def test_actionable_root_cause_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        RootCauseDecision(
            root_cause="unsupported claim",
            confidence=0.99,
            evidence_ids=[],
            rejected_hypotheses=[],
            uncertainty=[],
            safe_to_plan=True,
        )


def test_specialist_fanout_can_be_removed_by_configuration() -> None:
    settings = Settings(_env_file=EXAMPLE_ENV, specialist_names=[])
    assert settings.specialist_names == []


def test_specialist_cannot_shadow_a_control_node() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=EXAMPLE_ENV, specialist_names=["plan"])


def test_plan_hash_is_stable_and_binds_arguments() -> None:
    first = _plan()
    second = _plan()
    assert plan_hash(first) == plan_hash(second)
    second.actions[0].arguments["resource_id"] = "resource-2"
    assert plan_hash(first) != plan_hash(second)


def test_plan_target_must_exist_in_trusted_context(tmp_path: Path) -> None:
    catalog, policy = _write_documents(tmp_path)
    decision = ToolRegistry(catalog, policy).evaluate(_plan(), {"different-resource"})
    assert not decision.allowed
    assert "controller.change" in decision.blocked_actions


def test_tool_arguments_must_match_declared_target(tmp_path: Path) -> None:
    catalog, policy = _write_documents(tmp_path)
    action = _action()
    action.target_resource_ids = ["resource-2"]
    plan = _plan(action)
    plan.blast_radius = ["resource-2"]
    decision = ToolRegistry(catalog, policy).evaluate(plan, {"resource-2"})
    assert not decision.allowed
    assert "controller.change" in decision.blocked_actions


@pytest.mark.asyncio
async def test_executor_refuses_write_without_human_approval(tmp_path: Path) -> None:
    catalog, policy = _write_documents(tmp_path)
    registry = ToolRegistry(catalog, policy)
    executor = ToolExecutor(cast(Settings, cast(Any, object())), registry)
    with pytest.raises(PermissionError):
        await executor.execute(
            action=_action(),
            tenant_id="tenant-a",
            incident_id=str(uuid4()),
            expected_plan_hash=plan_hash(_plan()),
            approval=None,
            sequence=1,
        )


@pytest.mark.asyncio
async def test_executor_rejects_approval_for_a_different_plan(tmp_path: Path) -> None:
    catalog, policy = _write_documents(tmp_path)
    registry = ToolRegistry(catalog, policy)
    executor = ToolExecutor(cast(Settings, cast(Any, object())), registry)
    approval = ApprovalDecision(
        approved=True,
        actor="operator",
        plan_hash="0" * 64,
        reason="test",
        decided_at=datetime.now(UTC),
    )
    with pytest.raises(PermissionError):
        await executor.execute(
            action=_action(),
            tenant_id="tenant-a",
            incident_id=str(uuid4()),
            expected_plan_hash="1" * 64,
            approval=approval,
            sequence=1,
        )
