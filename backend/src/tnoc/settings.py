from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test", "staging", "production"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    api_host: str
    api_port: int = Field(gt=0, lt=65536)

    database_url: str
    checkpoint_database_url: str
    redis_url: str
    kafka_bootstrap_servers: str
    kafka_consumer_group: str
    telemetry_topic: str
    incident_topic: str
    decision_topic: str
    knowledge_topic: str
    event_stream_channel: str
    sse_heartbeat_seconds: float = Field(gt=0)
    outbox_poll_interval_seconds: float = Field(gt=0)
    outbox_batch_size: int = Field(gt=0)
    worker_retry_delay_seconds: float = Field(gt=0)
    worker_retry_backoff_multiplier: float = Field(ge=1)
    worker_retry_max_delay_seconds: float = Field(gt=0)
    worker_max_attempts: int = Field(gt=0)
    kafka_auto_offset_reset: Literal["earliest", "latest"]
    dead_letter_topic: str
    database_pool_recycle_seconds: int = Field(gt=0)

    correlation_window_seconds: int = Field(gt=0)
    correlation_min_event_count: int = Field(gt=0)
    dashboard_window_seconds: int = Field(gt=0)
    dashboard_rate_window_seconds: int = Field(gt=0)
    dashboard_incident_limit: int = Field(gt=0)

    llm_provider: str
    llm_model: str
    llm_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"]
    openai_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    openai_store: bool
    model_max_concurrency: int = Field(default=4, gt=0)
    model_requests_per_minute: int = Field(default=30, gt=0)
    model_timeout_seconds: float = Field(default=90, gt=0)
    model_max_retries: int = Field(default=2, ge=0, le=10)
    model_retry_base_seconds: float = Field(default=1, gt=0)
    model_run_log_directory: Path = Path("artifacts/model-runs")
    embedding_provider: str
    embedding_model: str
    rag_enabled: bool

    qdrant_url: str
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str
    rag_chunk_characters: int = Field(gt=0)
    rag_chunk_overlap_characters: int = Field(ge=0)
    rag_result_limit: int = Field(gt=0)

    prompt_directory: Path
    specialist_names: list[str]
    tool_catalog_path: Path
    policy_path: Path

    oidc_jwks_url: str
    oidc_issuer: str
    oidc_audience: str
    oidc_required: bool
    development_tenant_id: str | None = None
    allowed_origins: list[str]

    http_tool_connect_timeout_seconds: float = Field(gt=0)
    http_tool_read_timeout_seconds: float = Field(gt=0)
    max_tool_response_bytes: int = Field(gt=0)
    max_ingest_payload_bytes: int = Field(gt=0)
    max_knowledge_document_bytes: int = Field(gt=0)
    max_observation_future_skew_seconds: int = Field(ge=0)
    max_context_events: int = Field(gt=0)
    max_context_evidence: int = Field(gt=0)

    otel_service_name: str
    otel_exporter_otlp_endpoint: str
    otel_exporter_otlp_insecure: bool
    otel_trace_sample_ratio: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_security_and_topology(self) -> Settings:
        if self.rag_chunk_overlap_characters >= self.rag_chunk_characters:
            raise ValueError("RAG overlap must be smaller than chunk size")
        if len(set(self.specialist_names)) != len(self.specialist_names):
            raise ValueError("Specialist names must be unique")
        if any(not re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in self.specialist_names):
            raise ValueError("Specialist names must be safe prompt identifiers")
        graph_nodes = {
            "load_context",
            "adjudicate",
            "plan",
            "policy",
            "approval",
            "execute",
            "finalize",
        }
        if graph_nodes.intersection(self.specialist_names):
            raise ValueError("Specialist names cannot collide with workflow node names")
        topics = {
            self.telemetry_topic,
            self.incident_topic,
            self.decision_topic,
            self.knowledge_topic,
            self.dead_letter_topic,
        }
        if len(topics) != 5:
            raise ValueError("Kafka topics must be distinct")
        if self.environment == "production":
            if not self.oidc_required:
                raise ValueError("OIDC cannot be disabled in production")
            if self.development_tenant_id:
                raise ValueError("Development tenant must be unset in production")
            if not self.oidc_jwks_url.startswith("https://"):
                raise ValueError("Production JWKS endpoint must use HTTPS")
            if "*" in self.allowed_origins:
                raise ValueError("Wildcard CORS origin is forbidden in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
