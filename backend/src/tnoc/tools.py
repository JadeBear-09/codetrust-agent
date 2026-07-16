from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

import httpx
import orjson
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tnoc.domain import ApprovalDecision, PolicyDecision, RemediationPlan, SideEffect, ToolResult
from tnoc.settings import Settings


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]+$")
    description: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    base_url_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    authorization_token_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]+$")
    path: str = Field(pattern=r"^/")
    side_effect: SideEffect
    requires_approval: bool
    target_argument_fields: list[str] = Field(default_factory=list)
    request_schema: dict[str, Any]
    response_schema: dict[str, Any] | None = None
    result_fields: list[str] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def reject_ambiguous_destination_path(cls, value: str) -> str:
        parsed = urlparse(value)
        if (
            value.startswith("//")
            or parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or "\\" in value
            or any(segment == ".." for segment in value.split("/"))
        ):
            raise ValueError("Tool path must be an absolute, host-relative path")
        return value

    @model_validator(mode="after")
    def prevent_write_methods_from_claiming_read_only(self) -> ToolDefinition:
        if self.method in {"PUT", "PATCH", "DELETE"} and self.side_effect is SideEffect.READ:
            raise ValueError("Mutating HTTP methods cannot be classified as read-only")
        return self

    @field_validator("target_argument_fields")
    @classmethod
    def validate_target_argument_fields(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(
            not field or not field.replace("_", "a").isalnum() for field in value
        ):
            raise ValueError("Target argument fields must be unique flat JSON object keys")
        return value


class ToolCatalogDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    tools: list[ToolDefinition]


class PolicyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    default_write_policy: Literal["require_approval", "deny"]
    default_destructive_policy: Literal["require_approval", "deny"]
    required_plan_fields: list[str]
    auto_approve_tools: list[str]
    denied_tools: list[str]


class ToolRegistry:
    def __init__(self, catalog_path: Path, policy_path: Path, *, production: bool = False) -> None:
        catalog = ToolCatalogDocument.model_validate_json(catalog_path.read_text(encoding="utf-8"))
        self.policy = PolicyDocument.model_validate_json(policy_path.read_text(encoding="utf-8"))
        self._tools = {tool.name: tool for tool in catalog.tools}
        if len(self._tools) != len(catalog.tools):
            raise ValueError("Tool catalog contains duplicate names")
        if production and self.policy.auto_approve_tools:
            raise ValueError("Production policy cannot auto-approve tools")
        if production and self.policy.default_destructive_policy != "deny":
            raise ValueError("Production policy must deny destructive tools")
        for tool in catalog.tools:
            Draft202012Validator.check_schema(tool.request_schema)
            if tool.response_schema is not None:
                Draft202012Validator.check_schema(tool.response_schema)

    def catalog_for_model(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "side_effect": tool.side_effect.value,
                "requires_approval": tool.requires_approval,
                "target_argument_fields": tool.target_argument_fields,
                "request_schema": tool.request_schema,
            }
            for tool in self._tools.values()
        ]

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ValueError(f"Tool is not allowlisted: {name}") from exc

    @property
    def has_tools(self) -> bool:
        return bool(self._tools)

    def evaluate(self, plan: RemediationPlan, trusted_resource_ids: set[str]) -> PolicyDecision:
        reasons: list[str] = []
        blocked: list[str] = []
        requires_approval = plan.requires_approval

        for field_name in self.policy.required_plan_fields:
            if not hasattr(plan, field_name) or not getattr(plan, field_name):
                blocked.append(field_name)
                reasons.append(f"Required plan field is empty or unknown: {field_name}")

        for action in plan.actions:
            declared_targets = set(action.target_resource_ids)
            if not declared_targets.issubset(set(plan.blast_radius)):
                blocked.append(action.tool_name)
                reasons.append(f"Action targets exceed declared blast radius: {action.tool_name}")
            if not declared_targets.issubset(trusted_resource_ids):
                blocked.append(action.tool_name)
                reasons.append(
                    f"Action targets are absent from trusted incident context: {action.tool_name}"
                )
            try:
                tool = self.get(action.tool_name)
            except ValueError:
                blocked.append(action.tool_name)
                reasons.append(f"Unknown tool: {action.tool_name}")
                continue
            self._validate_target_binding(
                tool, action.arguments, declared_targets, blocked, reasons
            )
            if tool.name in self.policy.denied_tools:
                blocked.append(tool.name)
                reasons.append(f"Policy denies tool: {tool.name}")
            if tool.side_effect is SideEffect.DESTRUCTIVE:
                if self.policy.default_destructive_policy == "deny":
                    blocked.append(tool.name)
                    reasons.append(f"Destructive tool denied: {tool.name}")
                else:
                    requires_approval = True
            if tool.side_effect is SideEffect.WRITE:
                if self.policy.default_write_policy == "deny":
                    blocked.append(tool.name)
                    reasons.append(f"Write tool denied: {tool.name}")
                elif tool.name not in self.policy.auto_approve_tools:
                    requires_approval = True
            if tool.requires_approval:
                requires_approval = True
            Draft202012Validator(tool.request_schema).validate(action.arguments)
            try:
                verification = self.get(action.verification_tool_name)
            except ValueError:
                blocked.append(action.verification_tool_name)
                reasons.append(f"Unknown verification tool: {action.verification_tool_name}")
            else:
                if not verification.target_argument_fields:
                    blocked.append(verification.name)
                    reasons.append(
                        f"Verification tool lacks target binding fields: {verification.name}"
                    )
                self._validate_target_binding(
                    verification,
                    action.verification_arguments,
                    declared_targets,
                    blocked,
                    reasons,
                )
                if verification.side_effect is not SideEffect.READ:
                    blocked.append(verification.name)
                    reasons.append(f"Verification tool must be read-only: {verification.name}")
                if verification.response_schema is None:
                    blocked.append(verification.name)
                    reasons.append(
                        "Verification tool requires a deterministic response schema: "
                        f"{verification.name}"
                    )
                Draft202012Validator(verification.request_schema).validate(
                    action.verification_arguments
                )
            if action.rollback_tool_name:
                try:
                    rollback = self.get(action.rollback_tool_name)
                except ValueError:
                    blocked.append(action.rollback_tool_name)
                    reasons.append(f"Unknown rollback tool: {action.rollback_tool_name}")
                else:
                    self._validate_target_binding(
                        rollback,
                        action.rollback_arguments or {},
                        declared_targets,
                        blocked,
                        reasons,
                    )
                    if rollback.side_effect is SideEffect.DESTRUCTIVE:
                        blocked.append(rollback.name)
                        reasons.append(f"Destructive rollback denied: {rollback.name}")
                    if action.rollback_arguments is None:
                        blocked.append(rollback.name)
                        reasons.append(f"Rollback arguments missing: {rollback.name}")
                    else:
                        Draft202012Validator(rollback.request_schema).validate(
                            action.rollback_arguments
                        )
                    try:
                        rollback_verifier = self.get(action.rollback_verification_tool_name or "")
                    except ValueError:
                        blocked.append(action.rollback_verification_tool_name or "")
                        reasons.append("Unknown rollback verification tool")
                    else:
                        if not rollback_verifier.target_argument_fields:
                            blocked.append(rollback_verifier.name)
                            reasons.append(
                                "Rollback verification tool lacks target binding fields: "
                                f"{rollback_verifier.name}"
                            )
                        self._validate_target_binding(
                            rollback_verifier,
                            action.rollback_verification_arguments or {},
                            declared_targets,
                            blocked,
                            reasons,
                        )
                        if rollback_verifier.side_effect is not SideEffect.READ:
                            blocked.append(rollback_verifier.name)
                            reasons.append(
                                f"Rollback verification must be read-only: {rollback_verifier.name}"
                            )
                        if rollback_verifier.response_schema is None:
                            blocked.append(rollback_verifier.name)
                            reasons.append(
                                "Rollback verifier requires a deterministic response schema: "
                                f"{rollback_verifier.name}"
                            )
                        Draft202012Validator(rollback_verifier.request_schema).validate(
                            action.rollback_verification_arguments
                        )
            elif tool.side_effect is SideEffect.WRITE:
                blocked.append(tool.name)
                reasons.append(f"Write action lacks rollback: {tool.name}")

        return PolicyDecision(
            allowed=not blocked,
            requires_approval=requires_approval,
            reasons=reasons,
            blocked_actions=blocked,
        )

    @staticmethod
    def _validate_target_binding(
        tool: ToolDefinition,
        arguments: dict[str, Any],
        declared_targets: set[str],
        blocked: list[str],
        reasons: list[str],
    ) -> None:
        if tool.side_effect is not SideEffect.READ and not tool.target_argument_fields:
            blocked.append(tool.name)
            reasons.append(f"Side-effecting tool lacks target binding fields: {tool.name}")
            return
        if not tool.target_argument_fields:
            return
        values: set[str] = set()
        for field in tool.target_argument_fields:
            value = arguments.get(field)
            if isinstance(value, str):
                values.add(value)
            elif isinstance(value, list) and value and all(isinstance(item, str) for item in value):
                values.update(value)
            else:
                blocked.append(tool.name)
                reasons.append(f"Target field is missing or invalid: {tool.name}.{field}")
                return
        if values != declared_targets:
            blocked.append(tool.name)
            reasons.append(f"Tool arguments do not bind exact declared targets: {tool.name}")


def plan_hash(plan: RemediationPlan) -> str:
    canonical = orjson.dumps(plan.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(canonical).hexdigest()


class ToolExecutor:
    def __init__(self, settings: Settings, registry: ToolRegistry) -> None:
        self._settings = settings
        self._registry = registry

    async def execute(
        self,
        *,
        action: Any,
        tenant_id: str,
        incident_id: str,
        expected_plan_hash: str,
        approval: ApprovalDecision | None,
        sequence: int,
    ) -> ToolResult:
        tool = self._registry.get(action.tool_name)
        Draft202012Validator(tool.request_schema).validate(action.arguments)
        if tool.side_effect is not SideEffect.READ:
            if approval is None or not approval.approved:
                raise PermissionError("Approved decision required for side-effecting tool")
            if approval.plan_hash != expected_plan_hash:
                raise PermissionError("Approval does not bind the executed plan hash")

        base_url = os.environ.get(tool.base_url_env)
        if not base_url:
            raise RuntimeError(f"Tool endpoint environment variable is unset: {tool.base_url_env}")
        parsed = urlparse(base_url)
        if parsed.scheme != "https" and self._settings.environment == "production":
            raise RuntimeError("Production tool endpoints must use HTTPS")
        if parsed.username or parsed.password or not parsed.hostname:
            raise RuntimeError("Invalid tool endpoint")

        key_material = f"{tenant_id}:{incident_id}:{expected_plan_hash}:{sequence}:{tool.name}"
        idempotency_key = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
        started_at = datetime.now(UTC)
        headers = {
            "Idempotency-Key": idempotency_key,
            "X-Tenant-ID": tenant_id,
            "X-Incident-ID": incident_id,
            "X-Plan-Hash": expected_plan_hash,
        }
        if tool.authorization_token_env:
            token = os.environ.get(tool.authorization_token_env)
            if not token:
                raise RuntimeError(
                    "Tool authorization environment variable is unset: "
                    f"{tool.authorization_token_env}"
                )
            headers["Authorization"] = f"Bearer {token}"
        timeout = httpx.Timeout(
            connect=self._settings.http_tool_connect_timeout_seconds,
            read=self._settings.http_tool_read_timeout_seconds,
            write=self._settings.http_tool_read_timeout_seconds,
            pool=self._settings.http_tool_connect_timeout_seconds,
        )
        url = urljoin(base_url.rstrip("/") + "/", tool.path.lstrip("/"))

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                kwargs = (
                    {"params": action.arguments}
                    if tool.method == "GET"
                    else {"json": action.arguments}
                )
                async with client.stream(tool.method, url, headers=headers, **kwargs) as response:
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self._settings.max_tool_response_bytes:
                            raise RuntimeError("Tool response exceeded configured size limit")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    try:
                        output = json.loads(raw) if raw else {}
                    except json.JSONDecodeError:
                        output = {
                            "content_sha256": hashlib.sha256(raw).hexdigest(),
                            "content_type": response.headers.get("content-type"),
                        }
                    if not isinstance(output, dict):
                        output = {"value": output}
                    if tool.response_schema is not None:
                        Draft202012Validator(tool.response_schema).validate(output)
                    safe_output = {key: output[key] for key in tool.result_fields if key in output}
                    safe_output["response_sha256"] = hashlib.sha256(
                        orjson.dumps(output, option=orjson.OPT_SORT_KEYS)
                    ).hexdigest()
                    ok = 200 <= response.status_code < 300
                    return ToolResult(
                        tool_name=tool.name,
                        idempotency_key=idempotency_key,
                        ok=ok,
                        status_code=response.status_code,
                        output=safe_output,
                        error=None if ok else "Tool returned non-success status",
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                    )
        except Exception as exc:
            return ToolResult(
                tool_name=tool.name,
                idempotency_key=idempotency_key,
                ok=False,
                output={},
                error=type(exc).__name__,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
