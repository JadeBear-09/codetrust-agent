from __future__ import annotations

import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from codetrust.agent import verify_change
from codetrust.github import load_pull_request, load_repository_policy, repository_policy_paths
from codetrust.llm import SynthesisError, model_status
from codetrust.models import InterpretationClaim
from codetrust.run_store import get_run, list_runs, save_run
from codetrust.scope import parse_intent_snapshot
from codetrust.ui import DASHBOARD_HTML


class InterpretationInput(BaseModel):
    role: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4_000)
    source: str = Field(default="", max_length=500)


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket: str = Field(min_length=1, max_length=20_000)
    diff: str = Field(min_length=1, max_length=500_000)
    model_mode: Literal["required", "disabled"] = "required"
    interpretations: list[InterpretationInput] = Field(default_factory=list, max_length=20)


class GitHubRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str = Field(min_length=3, max_length=500)
    intent: str = Field(default="", max_length=20_000)
    model_mode: Literal["required", "disabled"] = "required"


app = FastAPI(
    title="CodeTrust",
    version="0.4.0",
    description="Evidence-first verification API for software pull requests.",
)


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return DASHBOARD_HTML


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "codetrust"}


@app.get("/api/config")
def config() -> dict:
    return {
        "service": "codetrust",
        "version": app.version,
        "model": model_status(),
        "github_ingestion": "authenticated-gh-cli",
    }


@app.get("/api/runs")
def runs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, list[dict]]:
    return {"runs": list_runs(limit)}


@app.get("/api/runs/{run_id}")
def run(run_id: str) -> dict:
    try:
        return get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/verify")
def verify(request: VerifyRequest) -> dict:
    started = time.monotonic()
    _require_structured_intent(request.ticket)
    try:
        report = verify_change(
            request.ticket,
            request.diff,
            offline=request.model_mode == "disabled",
            source={"type": "dashboard-diff", "intent_source": "provided"},
            interpretations=[
                InterpretationClaim(role=item.role, text=item.text, source=item.source)
                for item in request.interpretations
            ],
        ).to_dict()
    except SynthesisError as exc:
        raise HTTPException(status_code=502, detail=exc.to_dict()) from exc
    report["duration_ms"] = round((time.monotonic() - started) * 1000)
    _save_run(report)
    return report


@app.post("/api/github")
def verify_github(request: GitHubRequest) -> dict:
    started = time.monotonic()
    try:
        change = load_pull_request(request.reference)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    supplied_intent = request.intent.strip()
    policy = None
    if not supplied_intent:
        try:
            policy = load_repository_policy(change.repo, change.base_sha)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if policy is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "MISSING_APPROVED_INTENT",
                    "message": (
                        "No approved policy found on the PR base commit. "
                        "Add CODETRUST.md to the base branch or provide approved intent under Advanced."
                    ),
                    "searched_paths": list(repository_policy_paths()),
                },
            )
    approved_intent = supplied_intent or policy.content
    _require_structured_intent(approved_intent)
    source = {
        "type": "github-pr",
        "reference": f"{change.repo}#{change.number}",
        "repo": change.repo,
        "number": str(change.number),
        "url": change.url,
        "state": change.state,
        "author": change.author,
        "base_sha": change.base_sha,
        "head_sha": change.head_sha,
        "intent_source": "provided" if supplied_intent else "repository-policy",
    }
    if policy is not None:
        source.update(intent_path=policy.path, intent_sha256=policy.sha256)
    try:
        report = verify_change(
            approved_intent,
            change.diff,
            offline=request.model_mode == "disabled",
            source=source,
        ).to_dict()
    except SynthesisError as exc:
        raise HTTPException(status_code=502, detail=exc.to_dict()) from exc
    report["duration_ms"] = round((time.monotonic() - started) * 1000)
    _save_run(report)
    return report


def _save_run(report: dict) -> None:
    try:
        save_run(report)
    except (OSError, ValueError):
        # Verification result remains available even when local history cannot be written.
        return


def _require_structured_intent(intent: str) -> None:
    snapshot = parse_intent_snapshot(intent)
    if any(
        (
            snapshot.outcome,
            snapshot.in_scope,
            snapshot.out_of_scope,
            snapshot.acceptance_criteria,
        )
    ):
        return
    raise HTTPException(
        status_code=422,
        detail={
            "code": "INVALID_APPROVED_INTENT",
            "message": (
                "Approved intent needs at least one heading: Outcome, In scope, "
                "Out of scope, or Acceptance criteria."
            ),
        },
    )


def run_server(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")
