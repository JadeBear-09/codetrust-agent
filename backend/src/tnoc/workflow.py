from __future__ import annotations

import operator
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, TypedDict, cast
from uuid import UUID

import orjson
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tnoc.domain import (
    ApprovalDecision,
    IncidentStatus,
    PolicyDecision,
    RemediationPlan,
    RootCauseDecision,
    SpecialistFinding,
    ToolAction,
    ToolResult,
)
from tnoc.llm import PromptRegistry
from tnoc.model_runtime import ModelRuntime
from tnoc.rag import KnowledgeRetriever
from tnoc.repository import Repository
from tnoc.settings import Settings
from tnoc.tools import ToolExecutor, ToolRegistry, plan_hash


class WorkflowState(TypedDict, total=False):
    tenant_id: str
    incident_id: str
    actor: str
    context: dict[str, Any]
    retrieved_context: list[dict[str, Any]]
    findings: Annotated[list[dict[str, Any]], operator.add]
    decision: dict[str, Any]
    plan: dict[str, Any]
    policy: dict[str, Any]
    approval: dict[str, Any]
    tool_results: list[dict[str, Any]]
    final_status: str
    error: str


class ChangeGuardWorkflow:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        model_runtime: ModelRuntime,
        prompts: PromptRegistry,
        knowledge: KnowledgeRetriever,
        registry: ToolRegistry,
        executor: ToolExecutor,
        checkpointer: Any,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.model_runtime = model_runtime
        self.prompts = prompts
        self.knowledge = knowledge
        self.registry = registry
        self.executor = executor
        self.graph = self._build().compile(checkpointer=checkpointer)

    def _build(self) -> StateGraph[WorkflowState]:
        builder = StateGraph(WorkflowState)
        builder.add_node("load_context", self.load_context)
        # LangGraph's current generic overload loses TypedDict state for generated callables.
        for specialist in self.settings.specialist_names:
            builder.add_node(specialist, cast(Any, self._specialist_node(specialist)))
        builder.add_node("adjudicate", self.adjudicate)
        builder.add_node("plan", self.plan)
        builder.add_node("policy", self.apply_policy)
        builder.add_node("approval", self.approval)
        builder.add_node("execute", self.execute)
        builder.add_node("finalize", self.finalize)

        builder.add_edge(START, "load_context")
        if self.settings.specialist_names:
            for node in self.settings.specialist_names:
                builder.add_edge("load_context", node)
            builder.add_edge(self.settings.specialist_names, "adjudicate")
        else:
            builder.add_edge("load_context", "adjudicate")
        builder.add_conditional_edges(
            "adjudicate",
            self._route_after_adjudication,
            {"plan": "plan", "finalize": "finalize"},
        )
        builder.add_edge("plan", "policy")
        builder.add_conditional_edges(
            "policy",
            self._route_after_policy,
            {"approval": "approval", "execute": "execute", "finalize": "finalize"},
        )
        builder.add_conditional_edges(
            "approval",
            lambda state: "execute" if state.get("approval", {}).get("approved") else "finalize",
            {"execute": "execute", "finalize": "finalize"},
        )
        builder.add_edge("execute", "finalize")
        builder.add_edge("finalize", END)
        return builder

    async def load_context(self, state: WorkflowState) -> dict[str, Any]:
        tenant_id = state["tenant_id"]
        incident_id = UUID(state["incident_id"])
        async with self.session_factory() as session:
            repository = Repository(session, self.settings)
            await repository.set_tenant_scope(tenant_id)
            bundle = await repository.incident_bundle(tenant_id, incident_id)
        query = " ".join(
            value
            for value in [
                bundle["incident"].get("title"),
                bundle["incident"].get("summary"),
                bundle["incident"].get("root_cause"),
            ]
            if value
        )
        retrieved = await self.knowledge.search(tenant_id, query)
        return {"context": self._shape_context(bundle), "retrieved_context": retrieved}

    def _specialist_node(self, name: str) -> Callable[[WorkflowState], Awaitable[dict[str, Any]]]:
        async def run(state: WorkflowState) -> dict[str, Any]:
            envelope = {
                "incident": state["context"],
                "retrieved_context": state.get("retrieved_context", []),
            }
            finding = await self.model_runtime.invoke(
                SpecialistFinding,
                [
                    SystemMessage(content=self.prompts.get(name)),
                    HumanMessage(
                        content="UNTRUSTED_CONTEXT\n" + orjson.dumps(envelope).decode("utf-8")
                    ),
                ],
                run_id=state["incident_id"],
                node=f"specialist:{name}",
                metadata={"tenant_id": state["tenant_id"], "specialist": name},
            )
            supplied_evidence = {UUID(item["id"]) for item in state["context"].get("evidence", [])}
            referenced_evidence = {
                evidence_id
                for hypothesis in finding.hypotheses
                for evidence_id in hypothesis.evidence_ids
            }
            if not referenced_evidence.issubset(supplied_evidence):
                raise ValueError("Specialist cited evidence outside the supplied evidence set")
            return {"findings": [finding.model_dump(mode="json")]}

        return run

    async def adjudicate(self, state: WorkflowState) -> dict[str, Any]:
        payload = {
            "evidence": state["context"].get("evidence", []),
            "findings": state.get("findings", []),
        }
        decision = await self.model_runtime.invoke(
            RootCauseDecision,
            [
                SystemMessage(content=self.prompts.get("adjudicator")),
                HumanMessage(content="UNTRUSTED_CONTEXT\n" + orjson.dumps(payload).decode("utf-8")),
            ],
            run_id=state["incident_id"],
            node="adjudicator",
            metadata={"tenant_id": state["tenant_id"]},
        )
        supplied_evidence = {UUID(item["id"]) for item in state["context"].get("evidence", [])}
        if not set(decision.evidence_ids).issubset(supplied_evidence):
            raise ValueError("Adjudicator cited evidence outside the supplied evidence set")
        return {"decision": decision.model_dump(mode="json")}

    async def plan(self, state: WorkflowState) -> dict[str, Any]:
        evidence_payload = {
            "decision": state["decision"],
            "evidence": state["context"].get("evidence", []),
            "topology": state["context"].get("topology", []),
        }
        trusted_catalog = self.registry.catalog_for_model()
        plan = await self.model_runtime.invoke(
            RemediationPlan,
            [
                SystemMessage(
                    content=self.prompts.get("planner")
                    + "\nTRUSTED_TOOL_CATALOG\n"
                    + orjson.dumps(trusted_catalog).decode("utf-8")
                ),
                HumanMessage(
                    content="UNTRUSTED_CONTEXT\n" + orjson.dumps(evidence_payload).decode("utf-8")
                ),
            ],
            run_id=state["incident_id"],
            node="planner",
            metadata={"tenant_id": state["tenant_id"]},
        )
        return {"plan": plan.model_dump(mode="json")}

    async def apply_policy(self, state: WorkflowState) -> dict[str, Any]:
        plan = RemediationPlan.model_validate(state["plan"])
        try:
            decision = self.registry.evaluate(plan, self._trusted_resource_ids(state))
        except Exception as exc:
            decision = PolicyDecision(
                allowed=False,
                requires_approval=False,
                reasons=[type(exc).__name__],
                blocked_actions=[action.tool_name for action in plan.actions],
            )
        return {"policy": decision.model_dump(mode="json")}

    async def approval(self, state: WorkflowState) -> dict[str, Any]:
        plan = RemediationPlan.model_validate(state["plan"])
        async with self.session_factory() as session:
            repository = Repository(session, self.settings)
            await repository.set_tenant_scope(state["tenant_id"])
            incident_id = UUID(state["incident_id"])
            current_status = await repository.incident_status(state["tenant_id"], incident_id)
            if current_status is not IncidentStatus.DECISION_SUBMITTED:
                await repository.save_remediation(
                    state["tenant_id"],
                    incident_id,
                    plan,
                    PolicyDecision.model_validate(state["policy"]),
                    IncidentStatus.AWAITING_APPROVAL.value,
                )
                await repository.set_incident_status(
                    state["tenant_id"], incident_id, IncidentStatus.AWAITING_APPROVAL
                )
            await session.commit()
        response = interrupt(
            {
                "type": "production_change_approval",
                "tenant_id": state["tenant_id"],
                "incident_id": state["incident_id"],
                "plan_hash": plan_hash(plan),
                "plan": plan.model_dump(mode="json"),
                "policy": state["policy"],
            }
        )
        decision = ApprovalDecision.model_validate(response)
        if decision.plan_hash != plan_hash(plan):
            raise ValueError("Approval plan hash does not match checkpointed plan")
        return {
            "approval": decision.model_dump(mode="json"),
        }

    async def execute(self, state: WorkflowState) -> dict[str, Any]:
        plan = RemediationPlan.model_validate(state["plan"])
        approval = (
            ApprovalDecision.model_validate(state["approval"]) if state.get("approval") else None
        )
        expected_hash = plan_hash(plan)
        results: list[ToolResult] = []
        completed: list[ToolAction] = []
        sequence = 0
        async with self.session_factory() as session:
            repository = Repository(session, self.settings)
            await repository.set_tenant_scope(state["tenant_id"])
            await repository.set_incident_status(
                state["tenant_id"], UUID(state["incident_id"]), IncidentStatus.EXECUTING
            )
            await session.commit()

        for action in plan.actions:
            sequence += 1
            result = await self.executor.execute(
                action=action,
                tenant_id=state["tenant_id"],
                incident_id=state["incident_id"],
                expected_plan_hash=expected_hash,
                approval=approval,
                sequence=sequence,
            )
            results.append(result)
            if not result.ok:
                break
            completed.append(action)

            sequence += 1
            verification = ToolAction(
                tool_name=action.verification_tool_name,
                arguments=action.verification_arguments,
                target_resource_ids=action.target_resource_ids,
                expected_result=action.expected_result,
                verification_tool_name=action.verification_tool_name,
                verification_arguments=action.verification_arguments,
            )
            verified = await self.executor.execute(
                action=verification,
                tenant_id=state["tenant_id"],
                incident_id=state["incident_id"],
                expected_plan_hash=expected_hash,
                approval=approval,
                sequence=sequence,
            )
            results.append(verified)
            if not verified.ok:
                break

        failed = any(not result.ok for result in results)
        if failed:
            for action in reversed(completed):
                if (
                    not action.rollback_tool_name
                    or action.rollback_arguments is None
                    or not action.rollback_verification_tool_name
                    or action.rollback_verification_arguments is None
                ):
                    continue
                sequence += 1
                rollback = ToolAction(
                    tool_name=action.rollback_tool_name,
                    arguments=action.rollback_arguments,
                    target_resource_ids=action.target_resource_ids,
                    expected_result="rollback accepted",
                    verification_tool_name=action.verification_tool_name,
                    verification_arguments=action.verification_arguments,
                )
                results.append(
                    await self.executor.execute(
                        action=rollback,
                        tenant_id=state["tenant_id"],
                        incident_id=state["incident_id"],
                        expected_plan_hash=expected_hash,
                        approval=approval,
                        sequence=sequence,
                    )
                )
                if not results[-1].ok:
                    continue
                sequence += 1
                rollback_verification = ToolAction(
                    tool_name=action.rollback_verification_tool_name,
                    arguments=action.rollback_verification_arguments,
                    target_resource_ids=action.target_resource_ids,
                    expected_result="rollback state verified",
                    verification_tool_name=action.rollback_verification_tool_name,
                    verification_arguments=action.rollback_verification_arguments,
                )
                results.append(
                    await self.executor.execute(
                        action=rollback_verification,
                        tenant_id=state["tenant_id"],
                        incident_id=state["incident_id"],
                        expected_plan_hash=expected_hash,
                        approval=approval,
                        sequence=sequence,
                    )
                )
        return {
            "tool_results": [item.model_dump(mode="json") for item in results],
            "final_status": IncidentStatus.FAILED.value
            if failed
            else IncidentStatus.RESOLVED.value,
        }

    async def finalize(self, state: WorkflowState) -> dict[str, Any]:
        tenant_id = state["tenant_id"]
        incident_id = UUID(state["incident_id"])
        decision = RootCauseDecision.model_validate(state["decision"])
        final_status_value = state.get("final_status")
        if final_status_value is None:
            if not state.get("plan"):
                final_status_value = IncidentStatus.DIAGNOSED.value
            elif state.get("policy") and not state["policy"].get("allowed"):
                final_status_value = IncidentStatus.REJECTED.value
            elif state.get("approval") and not state["approval"].get("approved"):
                final_status_value = IncidentStatus.REJECTED.value
            else:
                final_status_value = IncidentStatus.FAILED.value
        final_status = IncidentStatus(final_status_value)
        async with self.session_factory() as session:
            repository = Repository(session, self.settings)
            await repository.set_tenant_scope(tenant_id)
            await repository.save_root_cause(
                tenant_id, incident_id, decision.root_cause, decision.confidence
            )
            if state.get("plan") and state.get("policy"):
                await repository.save_remediation(
                    tenant_id,
                    incident_id,
                    RemediationPlan.model_validate(state["plan"]),
                    PolicyDecision.model_validate(state["policy"]),
                    final_status.value,
                    [ToolResult.model_validate(item) for item in state.get("tool_results", [])],
                    state.get("approval"),
                )
            await repository.set_incident_status(tenant_id, incident_id, final_status)
            await repository.append_audit(
                tenant_id=tenant_id,
                incident_id=incident_id,
                event_type="workflow.finalized",
                actor=state.get("actor", "system"),
                payload={
                    "decision": state["decision"],
                    "plan": state.get("plan"),
                    "policy": state.get("policy"),
                    "approval": state.get("approval"),
                    "tool_results": state.get("tool_results", []),
                    "status": final_status.value,
                },
            )
            await session.commit()
        return {"final_status": final_status.value}

    @staticmethod
    def _route_after_policy(state: WorkflowState) -> str:
        policy = state["policy"]
        if not policy.get("allowed"):
            return "finalize"
        return "approval" if policy.get("requires_approval") else "execute"

    def _route_after_adjudication(self, state: WorkflowState) -> str:
        if not state.get("decision", {}).get("safe_to_plan"):
            return "finalize"
        return "plan" if self.registry.has_tools else "finalize"

    @staticmethod
    def _trusted_resource_ids(state: WorkflowState) -> set[str]:
        context = state.get("context", {})
        incident = context.get("incident", {})
        trusted = {
            value for value in incident.get("service_ids", []) if isinstance(value, str) and value
        }
        for event in context.get("events", []):
            for field in ("resource_id", "service_id"):
                value = event.get(field)
                if isinstance(value, str) and value:
                    trusted.add(value)
        for relation in context.get("topology", []):
            for field in ("source_id", "target_id"):
                value = relation.get(field)
                if isinstance(value, str) and value:
                    trusted.add(value)
        return trusted

    @staticmethod
    def _shape_context(bundle: dict[str, Any]) -> dict[str, Any]:
        return {
            "incident": bundle["incident"],
            "events": [
                {
                    key: event.get(key)
                    for key in (
                        "id",
                        "source",
                        "domain",
                        "event_type",
                        "observed_at",
                        "severity",
                        "resource_id",
                        "service_id",
                        "summary",
                        "correlation_keys",
                        "trace_id",
                    )
                }
                for event in bundle["events"]
            ],
            "evidence": [
                {
                    key: evidence.get(key)
                    for key in (
                        "id",
                        "kind",
                        "source",
                        "statement",
                        "observed_at",
                        "checksum",
                    )
                }
                for evidence in bundle["evidence"]
            ],
            "topology": bundle["topology"],
        }
