from __future__ import annotations

import asyncio
import hashlib
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, TypeVar, cast

import orjson
import structlog
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, TypeAdapter

from tnoc.settings import Settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)
log = structlog.get_logger()


class RunLedger:
    """Append-only JSONL proof log. Secrets and raw prompts are intentionally excluded."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    async def emit(self, event: str, **payload: Any) -> None:
        record = {
            "observed_at": datetime.now(UTC).isoformat(),
            "event": event,
            **payload,
        }
        line = orjson.dumps(record, option=orjson.OPT_SORT_KEYS).decode("utf-8") + "\n"
        async with self._lock:
            await asyncio.to_thread(self._append, line)

    def _append(self, line: str) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)


class ModelRuntime:
    """Structured model calls with local quota control and reproducible metadata."""

    def __init__(
        self,
        settings: Settings,
        model: BaseChatModel,
        *,
        ledger: RunLedger | None = None,
        rate_window_seconds: float = 60,
    ) -> None:
        self._settings = settings
        self._model = model
        self._ledger = ledger
        self._rate_window_seconds = rate_window_seconds
        self._semaphore = asyncio.Semaphore(settings.model_max_concurrency)
        self._rate_lock = asyncio.Lock()
        self._request_starts: deque[float] = deque()

    async def invoke(
        self,
        schema: type[SchemaT],
        messages: list[BaseMessage],
        *,
        run_id: str,
        node: str,
        metadata: dict[str, Any] | None = None,
    ) -> SchemaT:
        structured = self._model.with_structured_output(
            schema,
            method="json_schema",
            strict=True,
            include_raw=True,
        )
        input_sha256 = hashlib.sha256(
            repr([(message.type, message.content) for message in messages]).encode("utf-8")
        ).hexdigest()
        safe_metadata = metadata or {}
        last_error: Exception | None = None

        for attempt in range(1, self._settings.model_max_retries + 2):
            wait_started = perf_counter()
            async with self._semaphore:
                await self._acquire_rate_slot()
                quota_wait_ms = (perf_counter() - wait_started) * 1000
                started = perf_counter()
                await self._emit(
                    "model_call_started",
                    run_id=run_id,
                    node=node,
                    attempt=attempt,
                    provider=self._settings.llm_provider,
                    model=self._settings.llm_model,
                    input_sha256=input_sha256,
                    quota_wait_ms=round(quota_wait_ms, 3),
                    metadata=safe_metadata,
                )
                try:
                    async with asyncio.timeout(self._settings.model_timeout_seconds):
                        bundle = await structured.ainvoke(messages)
                    if not isinstance(bundle, dict):
                        raise TypeError("Structured model response envelope must be an object")
                    parsing_error = bundle.get("parsing_error")
                    if parsing_error is not None:
                        raise ValueError("Structured model response failed schema parsing")
                    parsed = TypeAdapter(schema).validate_python(bundle.get("parsed"))
                    raw = bundle.get("raw")
                    usage = self._usage_metadata(raw)
                    output = parsed.model_dump(mode="json")
                    output_sha256 = hashlib.sha256(
                        orjson.dumps(output, option=orjson.OPT_SORT_KEYS)
                    ).hexdigest()
                    duration_ms = (perf_counter() - started) * 1000
                    await self._emit(
                        "model_call_completed",
                        run_id=run_id,
                        node=node,
                        attempt=attempt,
                        provider=self._settings.llm_provider,
                        model=self._settings.llm_model,
                        duration_ms=round(duration_ms, 3),
                        quota_wait_ms=round(quota_wait_ms, 3),
                        input_sha256=input_sha256,
                        output_sha256=output_sha256,
                        usage=usage,
                        metadata=safe_metadata,
                    )
                    return parsed
                except Exception as exc:
                    last_error = exc
                    duration_ms = (perf_counter() - started) * 1000
                    await self._emit(
                        "model_call_failed",
                        run_id=run_id,
                        node=node,
                        attempt=attempt,
                        provider=self._settings.llm_provider,
                        model=self._settings.llm_model,
                        duration_ms=round(duration_ms, 3),
                        input_sha256=input_sha256,
                        error_type=type(exc).__name__,
                        will_retry=attempt <= self._settings.model_max_retries,
                        metadata=safe_metadata,
                    )
            if attempt <= self._settings.model_max_retries:
                await asyncio.sleep(self._settings.model_retry_base_seconds * (2 ** (attempt - 1)))

        if last_error is None:
            raise RuntimeError("Model call failed without an exception")
        raise last_error

    async def _acquire_rate_slot(self) -> None:
        while True:
            async with self._rate_lock:
                now = asyncio.get_running_loop().time()
                while (
                    self._request_starts
                    and now - self._request_starts[0] >= self._rate_window_seconds
                ):
                    self._request_starts.popleft()
                if len(self._request_starts) < self._settings.model_requests_per_minute:
                    self._request_starts.append(now)
                    return
                wait_seconds = max(
                    0.001,
                    self._rate_window_seconds - (now - self._request_starts[0]),
                )
            await asyncio.sleep(wait_seconds)

    async def _emit(self, event: str, **payload: Any) -> None:
        if self._ledger is not None:
            await self._ledger.emit(event, **payload)
        log.info(event, **payload)

    @staticmethod
    def _usage_metadata(raw: Any) -> dict[str, Any]:
        usage = getattr(raw, "usage_metadata", None)
        return cast(dict[str, Any], usage) if isinstance(usage, dict) else {}
