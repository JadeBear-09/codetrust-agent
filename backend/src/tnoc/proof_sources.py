from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, status

from tnoc.proof_domain import SOURCE_NAMES, SourceName, load_incident_inputs

DEFAULT_CASE_PATH = Path("examples/incidents")
DEFAULT_SOURCE_TOKENS: dict[SourceName, str] = {
    source: os.environ.get(f"PROOF_{source.upper()}_TOKEN") or secrets.token_urlsafe(32)
    for source in SOURCE_NAMES
}


def create_proof_source_app(
    case_path: Path = DEFAULT_CASE_PATH,
    *,
    source_tokens: dict[SourceName, str] | None = None,
) -> FastAPI:
    cases = {case.id: case for case in load_incident_inputs(case_path)}
    tokens = source_tokens or DEFAULT_SOURCE_TOKENS
    token_roles = {token: source for source, token in tokens.items()}
    access_log: list[dict[str, Any]] = []
    result = FastAPI(title="T-NOC isolated proof sources", version="0.1.0")

    @result.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok", "boundary": "local-proof-only"}

    @result.get("/v1/{source}/{case_id}")
    async def read_source(
        source: SourceName,
        case_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        supplied_token = (
            authorization.removeprefix("Bearer ")
            if authorization and authorization.startswith("Bearer ")
            else None
        )
        token_role = token_roles.get(supplied_token or "")
        allowed = token_role == source
        access_log.append(
            {
                "source": source,
                "case_id": case_id,
                "credential_role": token_role or "unknown",
                "allowed": allowed,
            }
        )
        if token_role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Valid source credential required",
            )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Credential is not authorized for requested source",
            )
        case = cases.get(case_id)
        if case is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
        return {
            "case_id": case.id,
            "source": source,
            "evidence": [item.model_dump(mode="json") for item in case.sources.for_source(source)],
        }

    @result.get("/state")
    async def state() -> dict[str, Any]:
        return {
            "sandbox": True,
            "cases": len(cases),
            "access_count": len(access_log),
            "denied_count": sum(1 for item in access_log if not item["allowed"]),
            "access_log": access_log,
        }

    return result


app = create_proof_source_app(Path(os.environ.get("PROOF_CASES_PATH", str(DEFAULT_CASE_PATH))))


def run() -> None:
    if os.environ.get("ENVIRONMENT") == "production":
        raise RuntimeError("Proof source API cannot run in production")
    uvicorn.run(
        "tnoc.proof_sources:app",
        host="127.0.0.1",
        port=int(os.environ.get("PROOF_SOURCE_PORT", "8091")),
        reload=False,
    )


if __name__ == "__main__":
    run()
