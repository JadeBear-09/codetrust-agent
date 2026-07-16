from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import orjson
import redis.asyncio as redis
import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.structs import OffsetAndMetadata, TopicPartition
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tnoc.bus import EventBus
from tnoc.db import create_engine, create_session_factory
from tnoc.domain import ApprovalDecision, IncidentStatus
from tnoc.llm import PromptRegistry, build_chat_model
from tnoc.model_runtime import ModelRuntime
from tnoc.observability import configure_observability, instrument_database
from tnoc.rag import (
    KnowledgeIndex,
    KnowledgeRetriever,
    LangChainEmbeddingProvider,
    NullKnowledgeRetriever,
)
from tnoc.repository import Repository
from tnoc.settings import Settings, get_settings
from tnoc.tools import ToolExecutor, ToolRegistry
from tnoc.workflow import ChangeGuardWorkflow

log = structlog.get_logger()


async def serve() -> None:
    settings = get_settings()
    tracer_provider = configure_observability(settings, "worker")
    engine = create_engine(settings)
    instrument_database(engine, tracer_provider)
    session_factory = create_session_factory(engine)
    notifier = redis.from_url(settings.redis_url, decode_responses=True)
    knowledge_index: KnowledgeIndex | None = None
    knowledge: KnowledgeRetriever = NullKnowledgeRetriever()
    if settings.rag_enabled:
        embeddings = LangChainEmbeddingProvider(settings)
        knowledge_index = KnowledgeIndex(settings, embeddings)
        knowledge = knowledge_index
    registry = ToolRegistry(
        settings.tool_catalog_path,
        settings.policy_path,
        production=settings.environment == "production",
    )
    executor = ToolExecutor(settings, registry)
    model = build_chat_model(settings)
    model_runtime = ModelRuntime(settings, model)
    prompts = PromptRegistry(settings.prompt_directory)
    topics = [settings.telemetry_topic, settings.incident_topic, settings.decision_topic]
    if settings.rag_enabled:
        topics.append(settings.knowledge_topic)
    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        enable_auto_commit=False,
        value_deserializer=orjson.loads,
        auto_offset_reset=settings.kafka_auto_offset_reset,
    )
    dead_letter_bus = EventBus(settings)

    async with AsyncPostgresSaver.from_conn_string(
        settings.checkpoint_database_url
    ) as checkpointer:
        workflow = ChangeGuardWorkflow(
            settings=settings,
            session_factory=session_factory,
            model_runtime=model_runtime,
            prompts=prompts,
            knowledge=knowledge,
            registry=registry,
            executor=executor,
            checkpointer=checkpointer,
        )
        await dead_letter_bus.start()
        await consumer.start()
        try:
            async for message in consumer:
                payload = message.value
                succeeded = await _process_with_retry(
                    settings,
                    session_factory,
                    workflow,
                    knowledge_index,
                    dead_letter_bus,
                    message,
                )
                if succeeded and isinstance(payload, dict) and payload.get("tenant_id"):
                    channel = f"{settings.event_stream_channel}:{payload['tenant_id']}"
                    try:
                        await notifier.publish(
                            channel,
                            orjson.dumps(
                                {
                                    "type": "dashboard.invalidate",
                                    "message_id": payload.get("message_id"),
                                }
                            ).decode("utf-8"),
                        )
                    except Exception:
                        log.exception("dashboard_invalidation_failed", channel=channel)
                await consumer.commit(
                    {
                        TopicPartition(message.topic, message.partition): OffsetAndMetadata(
                            message.offset + 1, ""
                        )
                    }
                )
        finally:
            await consumer.stop()
            await dead_letter_bus.stop()
            await notifier.aclose()
            await engine.dispose()


async def _process_with_retry(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    workflow: ChangeGuardWorkflow,
    knowledge_index: KnowledgeIndex | None,
    dead_letter_bus: EventBus,
    message: Any,
) -> bool:
    last_error: Exception | None = None
    for attempt in range(1, settings.worker_max_attempts + 1):
        try:
            await _handle_message(settings, session_factory, workflow, knowledge_index, message)
            return True
        except Exception as exc:
            last_error = exc
            log.exception(
                "worker_message_attempt_failed",
                topic=message.topic,
                partition=message.partition,
                offset=message.offset,
                attempt=attempt,
            )
            if attempt < settings.worker_max_attempts:
                delay = min(
                    settings.worker_retry_max_delay_seconds,
                    settings.worker_retry_delay_seconds
                    * settings.worker_retry_backoff_multiplier ** (attempt - 1),
                )
                await asyncio.sleep(delay)

    dead_letter = {
        "source_topic": message.topic,
        "source_partition": message.partition,
        "source_offset": message.offset,
        "error_type": type(last_error).__name__ if last_error else "UnknownError",
        "payload": message.value,
    }
    while True:
        try:
            await dead_letter_bus.publish(
                settings.dead_letter_topic,
                f"{message.topic}:{message.partition}:{message.offset}",
                dead_letter,
            )
            return False
        except Exception:
            log.exception("dead_letter_publish_failed", topic=message.topic, offset=message.offset)
            await asyncio.sleep(settings.worker_retry_max_delay_seconds)


async def _handle_message(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    workflow: ChangeGuardWorkflow,
    knowledge_index: KnowledgeIndex | None,
    message: Any,
) -> None:
    payload = message.value
    if not isinstance(payload, dict):
        raise ValueError("Kafka payload must be an object")
    if message.topic == settings.telemetry_topic:
        await _process_telemetry(settings, session_factory, payload)
    elif message.topic == settings.incident_topic:
        await workflow.graph.ainvoke(
            {
                "tenant_id": payload["tenant_id"],
                "incident_id": payload["incident_id"],
                "actor": "system",
                "findings": [],
            },
            config={"configurable": {"thread_id": payload["thread_id"]}},
        )
    elif message.topic == settings.decision_topic:
        decision = ApprovalDecision.model_validate(payload["decision"])
        workflow_status = await _approval_replay_status(
            settings, session_factory, payload, decision
        )
        config: RunnableConfig = {"configurable": {"thread_id": payload["thread_id"]}}
        if workflow_status is IncidentStatus.DECISION_SUBMITTED:
            resume_command: Command[Any] = Command(resume=decision.model_dump(mode="json"))
            await workflow.graph.ainvoke(resume_command, config=config)
        elif workflow_status in {IncidentStatus.EXECUTING, IncidentStatus.VERIFYING}:
            await workflow.graph.ainvoke(None, config=config)
    elif message.topic == settings.knowledge_topic:
        if knowledge_index is None:
            raise RuntimeError("Knowledge message received while RAG is disabled")
        await _process_knowledge(settings, session_factory, knowledge_index, payload)
    else:
        raise ValueError("Unsupported Kafka topic")


async def _process_telemetry(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    payload: dict[str, Any],
) -> None:
    async with session_factory() as session:
        repository = Repository(session, settings)
        await repository.set_tenant_scope(payload["tenant_id"])
        event = await repository.get_event(UUID(payload["event_id"]))
        incident, created, should_investigate = await repository.correlate_event(event)
        await repository.append_audit(
            tenant_id=event.tenant_id,
            incident_id=incident.id,
            event_type="incident.correlated",
            actor="system",
            payload={
                "event_id": str(event.id),
                "incident_id": str(incident.id),
                "created": created,
                "event_count": incident.event_count,
            },
        )
        if should_investigate:
            await repository.enqueue_outbox(
                tenant_id=event.tenant_id,
                topic=settings.incident_topic,
                message_key=str(incident.id),
                payload={
                    "tenant_id": event.tenant_id,
                    "incident_id": str(incident.id),
                    "thread_id": incident.workflow_thread_id,
                },
            )
        await session.commit()


async def _process_knowledge(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    knowledge: KnowledgeIndex,
    payload: dict[str, Any],
) -> None:
    async with session_factory() as session:
        repository = Repository(session, settings)
        await repository.set_tenant_scope(payload["tenant_id"])
        document = await repository.get_knowledge(
            payload["tenant_id"], UUID(payload["document_id"])
        )
        await knowledge.index_document(
            document_id=document.id,
            tenant_id=document.tenant_id,
            title=document.title,
            source_uri=document.source_uri,
            text=document.content,
            metadata=document.metadata_,
        )
        await repository.append_audit(
            tenant_id=document.tenant_id,
            incident_id=None,
            event_type="knowledge.indexed",
            actor="system",
            payload={"document_id": str(document.id), "content_sha256": document.content_sha256},
        )
        await session.commit()


async def _approval_replay_status(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    payload: dict[str, Any],
    decision: ApprovalDecision,
) -> IncidentStatus:
    async with session_factory() as session:
        repository = Repository(session, settings)
        await repository.set_tenant_scope(payload["tenant_id"])
        return await repository.approval_replay_status(
            payload["tenant_id"], payload["thread_id"], decision.plan_hash
        )


def run() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    run()
