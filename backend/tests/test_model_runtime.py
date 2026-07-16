from __future__ import annotations

import asyncio
import json
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any, cast

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from tnoc.model_runtime import ModelRuntime, RunLedger
from tnoc.proof_domain import SourceFinding
from tnoc.settings import Settings

EXAMPLE_ENV = Path(__file__).parents[1] / ".env.example"


class FakeStructuredRunnable:
    def __init__(self, delay: float = 0.01) -> None:
        self.delay = delay
        self.active = 0
        self.maximum_active = 0
        self.starts: list[float] = []

    async def ainvoke(self, messages: Any) -> dict[str, Any]:
        self.starts.append(perf_counter())
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        await asyncio.sleep(self.delay)
        self.active -= 1
        return {
            "parsed": SourceFinding(
                specialist="telemetry",
                candidate_codes=["capacity_congestion"],
                evidence_ids=["tel.capacity.1"],
                summary="bounded fake result",
                confidence=0.8,
                uncertainty=[],
            ),
            "raw": SimpleNamespace(
                usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
            ),
            "parsing_error": None,
        }


class FakeModel:
    def __init__(self, runnable: FakeStructuredRunnable) -> None:
        self.runnable = runnable

    def with_structured_output(self, *args: Any, **kwargs: Any) -> FakeStructuredRunnable:
        return self.runnable


def settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=EXAMPLE_ENV,
        model_max_retries=0,
        model_timeout_seconds=1,
        **overrides,
    )


@pytest.mark.asyncio
async def test_runtime_bounds_concurrency_and_writes_usage_ledger(tmp_path: Path) -> None:
    runnable = FakeStructuredRunnable()
    ledger = RunLedger(tmp_path / "run.jsonl")
    runtime = ModelRuntime(
        settings(model_max_concurrency=2, model_requests_per_minute=100),
        cast(BaseChatModel, cast(Any, FakeModel(runnable))),
        ledger=ledger,
    )

    await asyncio.gather(
        *(
            runtime.invoke(
                SourceFinding,
                [HumanMessage(content=f"case-{index}")],
                run_id="rate-test",
                node=f"specialist:{index}",
            )
            for index in range(4)
        )
    )

    records = [json.loads(line) for line in ledger.path.read_text().splitlines()]
    completed = [record for record in records if record["event"] == "model_call_completed"]
    assert runnable.maximum_active == 2
    assert len(completed) == 4
    assert all(record["usage"]["total_tokens"] == 15 for record in completed)


@pytest.mark.asyncio
async def test_runtime_enforces_request_window() -> None:
    runnable = FakeStructuredRunnable(delay=0)
    runtime = ModelRuntime(
        settings(model_max_concurrency=2, model_requests_per_minute=1),
        cast(BaseChatModel, cast(Any, FakeModel(runnable))),
        rate_window_seconds=0.05,
    )

    await asyncio.gather(
        runtime.invoke(
            SourceFinding,
            [HumanMessage(content="first")],
            run_id="window-test",
            node="first",
        ),
        runtime.invoke(
            SourceFinding,
            [HumanMessage(content="second")],
            run_id="window-test",
            node="second",
        ),
    )

    assert len(runnable.starts) == 2
    assert runnable.starts[1] - runnable.starts[0] >= 0.045
