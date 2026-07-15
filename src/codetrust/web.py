from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from codetrust.agent import verify_change
from codetrust.github import load_pull_request
from codetrust.llm import model_status
from codetrust.models import InterpretationClaim
from codetrust.run_store import get_run, list_runs, save_run
from codetrust.ui import DASHBOARD_HTML


class InterpretationInput(BaseModel):
    role: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4_000)
    source: str = Field(default="", max_length=500)


class VerifyRequest(BaseModel):
    ticket: str = Field(min_length=1, max_length=20_000)
    diff: str = Field(min_length=1, max_length=500_000)
    offline: bool = True
    interpretations: list[InterpretationInput] = Field(default_factory=list, max_length=20)


class GitHubRequest(BaseModel):
    reference: str = Field(min_length=3, max_length=500)
    intent: str = Field(default="", max_length=20_000)
    offline: bool = False


app = FastAPI(
    title="CodeTrust",
    version="0.3.0",
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


@app.get("/api/demo")
def demo() -> dict[str, str]:
    """Explicit offline fixture endpoint. Product UI never loads it automatically."""
    root = Path.cwd()
    ticket = root / "demo/tickets/payment-reconciliation.md"
    diff = root / "demo/patches/risky-payment.diff"
    if not ticket.exists() or not diff.exists():
        raise HTTPException(status_code=404, detail="Run server from CodeTrust repository root")
    return {"ticket": ticket.read_text(), "diff": diff.read_text()}


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
    report = verify_change(
        request.ticket,
        request.diff,
        offline=request.offline,
        source={"type": "dashboard-diff"},
        interpretations=[
            InterpretationClaim(role=item.role, text=item.text, source=item.source)
            for item in request.interpretations
        ],
    ).to_dict()
    _save_run(report)
    return report


@app.post("/api/github")
def verify_github(request: GitHubRequest) -> dict:
    try:
        change = load_pull_request(request.reference)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    supplied_intent = request.intent.strip()
    report = verify_change(
        supplied_intent or change.ticket,
        change.diff,
        offline=request.offline,
        source={
            "type": "github-pr",
            "reference": f"{change.repo}#{change.number}",
            "repo": change.repo,
            "number": str(change.number),
            "url": change.url,
            "state": change.state,
            "author": change.author,
            "base_sha": change.base_sha,
            "head_sha": change.head_sha,
            "intent_source": "provided" if supplied_intent else "pull-request",
        },
    ).to_dict()
    _save_run(report)
    return report


def _save_run(report: dict) -> None:
    try:
        save_run(report)
    except (OSError, ValueError):
        # Verification result remains available even when local history cannot be written.
        return


def run_server(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")
