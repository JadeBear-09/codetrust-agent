from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any

import structlog
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from sqlalchemy.ext.asyncio import AsyncEngine

from tnoc.settings import Settings


def _add_trace_context(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        event_dict["trace_id"] = format(span_context.trace_id, "032x")
        event_dict["span_id"] = format(span_context.span_id, "016x")
    return event_dict


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(level=settings.log_level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_trace_context,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def configure_observability(settings: Settings, service_suffix: str) -> TracerProvider:
    configure_logging(settings)
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        return current
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": f"{settings.otel_service_name}-{service_suffix}",
                "deployment.environment.name": settings.environment,
            }
        ),
        sampler=ParentBased(TraceIdRatioBased(settings.otel_trace_sample_ratio)),
    )
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=settings.otel_exporter_otlp_insecure,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    return provider


def instrument_fastapi(app: FastAPI, provider: TracerProvider) -> None:
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)


def instrument_database(engine: AsyncEngine, provider: TracerProvider) -> None:
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, tracer_provider=provider)
