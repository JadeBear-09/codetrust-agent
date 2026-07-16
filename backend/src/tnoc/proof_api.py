from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from tnoc.agent_mission import run_agent_mission_with_local_sources
from tnoc.model_runtime import RunLedger
from tnoc.proof_domain import SOURCE_NAMES, load_incident_inputs

RUN_ID_PATTERN = re.compile(r"^mission-[0-9]{8}T[0-9]{12}Z$")
DEFAULT_INCIDENTS_PATH = Path("examples/incidents")
DEFAULT_OUTPUT_ROOT = Path("../outputs/agent-missions")
MODEL_CALLS_PER_RUN = 6


class ProofRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["live"] = "live"
    model: str = Field(default="gemini-3.1-flash-lite", pattern=r"^[A-Za-z0-9._-]{3,128}$")
    incident_id: str = Field(
        default="ran-capacity-congestion",
        pattern=r"^[a-z0-9][a-z0-9_-]{2,127}$",
    )


class ProofRunService:
    def __init__(
        self,
        *,
        incidents_path: Path = DEFAULT_INCIDENTS_PATH,
        output_root: Path = DEFAULT_OUTPUT_ROOT,
    ) -> None:
        self.incidents_path = incidents_path
        self.output_root = output_root
        self.runs: dict[str, dict[str, Any]] = {}
        self.execution_lock = asyncio.Lock()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _run_id() -> str:
        return f"mission-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"

    @staticmethod
    def key_configured() -> bool:
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            return True
        env_path = Path(".env")
        if not env_path.exists():
            return False
        for line in env_path.read_text(encoding="utf-8").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() in {"GEMINI_API_KEY", "GOOGLE_API_KEY"}:
                return bool(value.strip().strip("'\""))
        return False

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        detail = str(exc)
        secrets = [
            value
            for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY")
            if (value := os.environ.get(name))
        ]
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                name, separator, value = line.partition("=")
                if separator and name.strip() in {"GEMINI_API_KEY", "GOOGLE_API_KEY"}:
                    normalized = value.strip().strip("'\"")
                    if normalized:
                        secrets.append(normalized)
        for secret in secrets:
            detail = detail.replace(secret, "[REDACTED]")
        return detail[:1000]

    def config(self) -> dict[str, Any]:
        incidents = load_incident_inputs(self.incidents_path)
        return {
            "service": "ChangeGuard Gemini multi-agent mission",
            "live_available": self.key_configured(),
            "default_model": "gemini-3.1-flash-lite",
            "model_calls_per_run": MODEL_CALLS_PER_RUN,
            "agents": [*SOURCE_NAMES, "adjudicator", "response_planner"],
            "incidents": [
                {
                    "id": incident.id,
                    "title": incident.title,
                    "description": incident.description,
                    "submitted_by": incident.submitted_by,
                    "submitted_at": incident.submitted_at.isoformat(),
                    "domain": incident.domain,
                    "resource_ids": incident.resource_ids,
                    "source_record_count": sum(
                        len(incident.sources.for_source(source)) for source in SOURCE_NAMES
                    ),
                    "file": f"examples/incidents/{index:02d}-{incident.id}.json",
                }
                for index, incident in enumerate(incidents, start=1)
            ],
            "truth_boundary": (
                "Live Gemini chooses findings, root cause, and response. Schema and citation "
                "validation reject invalid output but do not select answer. No controller executes."
            ),
            "logging": {
                "format": "JSONL",
                "agent_inputs_visible": True,
                "structured_outputs_visible": True,
                "raw_system_prompts_logged": False,
                "credentials_logged": False,
            },
        }

    def start(self, request: ProofRunRequest) -> dict[str, Any]:
        if not self.key_configured():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Live Gemini mode needs GEMINI_API_KEY or GOOGLE_API_KEY in backend/.env",
            )
        incident_ids = {item.id for item in load_incident_inputs(self.incidents_path)}
        if request.incident_id not in incident_ids:
            raise HTTPException(status_code=400, detail="Unknown incident ID")
        run_id = self._run_id()
        self.runs[run_id] = {
            "run_id": run_id,
            "status": "queued",
            "mode": "live_gemini_multi_agent",
            "model": request.model,
            "incident_id": request.incident_id,
            "started_at": self._now(),
            "completed_at": None,
            "error": None,
        }
        asyncio.create_task(self._execute(run_id, request))
        return self.read(run_id)

    async def _execute(self, run_id: str, request: ProofRunRequest) -> None:
        self.runs[run_id]["status"] = "running"
        try:
            async with self.execution_lock:
                await self._run_live(run_id, request.model, request.incident_id)
            self.runs[run_id]["status"] = "completed"
        except Exception as exc:
            safe_detail = self._safe_error(exc)
            self.runs[run_id]["status"] = "failed"
            self.runs[run_id]["error"] = f"{type(exc).__name__}: {safe_detail}"
            output_directory = self.output_root / run_id
            output_directory.mkdir(parents=True, exist_ok=True)
            await RunLedger(output_directory / "run.jsonl").emit(
                "mission_failed",
                run_id=run_id,
                error_type=type(exc).__name__,
                detail=safe_detail,
            )
        finally:
            self.runs[run_id]["completed_at"] = self._now()

    async def _run_live(self, run_id: str, model: str, incident_id: str) -> None:
        arguments = argparse.Namespace(
            incidents=self.incidents_path,
            output=self.output_root,
            model=model,
            max_concurrency=4,
            requests_per_minute=30,
            timeout=90.0,
            max_retries=2,
            source_base_url="http://127.0.0.1:8091",
            run_id=run_id,
            incident_id=incident_id,
        )
        await run_agent_mission_with_local_sources(arguments)

    def _directory(self, run_id: str) -> Path:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise HTTPException(status_code=400, detail="Invalid run ID")
        return self.output_root / run_id

    def read(self, run_id: str) -> dict[str, Any]:
        directory = self._directory(run_id)
        state = self.runs.get(run_id)
        if state is None and not directory.exists():
            raise HTTPException(status_code=404, detail="Mission not found")
        records: list[dict[str, Any]] = []
        log_path = directory / "run.jsonl"
        if log_path.exists():
            records = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        report = None
        summary_path = directory / "summary.json"
        if summary_path.exists():
            report = json.loads(summary_path.read_text(encoding="utf-8"))
        current = state or {
            "run_id": run_id,
            "status": "completed" if report else "failed",
            "mode": report.get("execution_mode") if report else "unknown",
            "model": report.get("model") if report else None,
            "incident_id": report.get("incident", {}).get("id") if report else None,
            "started_at": records[0].get("observed_at") if records else None,
            "completed_at": records[-1].get("observed_at") if records else None,
            "error": None,
        }
        return {
            **current,
            "progress": {
                "event_count": len(records),
                "completed_model_calls": sum(
                    1 for item in records if item.get("event") == "model_call_completed"
                ),
                "expected_model_calls": MODEL_CALLS_PER_RUN,
            },
            "events": records,
            "report": report,
            "log_url": f"/api/proof/runs/{run_id}/log",
        }

    def latest(self) -> dict[str, Any]:
        candidates = []
        for summary in self.output_root.glob("*/summary.json"):
            if not RUN_ID_PATTERN.fullmatch(summary.parent.name):
                continue
            try:
                payload = json.loads(summary.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("input_schema_version") == "agent-mission-v1":
                candidates.append(summary.parent)
        if not candidates:
            raise HTTPException(status_code=404, detail="No completed mission found")
        newest = max(candidates, key=lambda path: path.stat().st_mtime_ns)
        return self.read(newest.name)

    def log_path(self, run_id: str) -> Path:
        path = self._directory(run_id) / "run.jsonl"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Mission log not ready")
        return path


def create_app(service: ProofRunService | None = None) -> FastAPI:
    proof_service = service or ProofRunService()
    result = FastAPI(title="ChangeGuard Gemini multi-agent API", version="1.0.0")

    @result.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": "live-gemini-multi-agent-only"}

    @result.get("/v1/proof/config")
    async def config() -> dict[str, Any]:
        return proof_service.config()

    @result.post("/v1/proof/runs", status_code=status.HTTP_202_ACCEPTED)
    async def start_run(request: ProofRunRequest) -> dict[str, Any]:
        return proof_service.start(request)

    @result.get("/v1/proof/runs/latest")
    async def latest_run() -> dict[str, Any]:
        return proof_service.latest()

    @result.get("/v1/proof/runs/{run_id}")
    async def read_run(run_id: str) -> dict[str, Any]:
        return proof_service.read(run_id)

    @result.get("/v1/proof/runs/{run_id}/log")
    async def download_log(run_id: str) -> FileResponse:
        return FileResponse(
            proof_service.log_path(run_id),
            media_type="application/x-ndjson",
            filename=f"{run_id}.jsonl",
        )

    return result


app = create_app()


def run() -> None:
    if os.environ.get("ENVIRONMENT") == "production":
        raise RuntimeError("Local mission runner refuses to start in production")
    uvicorn.run(
        "tnoc.proof_api:app",
        host=os.environ.get("PROOF_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("PROOF_API_PORT", "8010")),
        reload=False,
    )


if __name__ == "__main__":
    run()
