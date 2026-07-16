from __future__ import annotations

import asyncio
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from tnoc.settings import Settings, get_settings


@dataclass(frozen=True, slots=True)
class AuthContext:
    subject: str
    tenant_id: str
    roles: frozenset[str]


_bearer = HTTPBearer(auto_error=False)
_jwk_clients: dict[str, PyJWKClient] = {}


async def authenticate(
    credentials: HTTPAuthorizationCredentials | None = None,
    x_tenant_id: str | None = Header(default=None),
    settings: Settings | None = None,
) -> AuthContext:
    settings = settings or get_settings()
    if not settings.oidc_required:
        tenant = settings.development_tenant_id
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OIDC disabled but no development tenant configured",
            )
        if x_tenant_id and x_tenant_id != tenant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Development tenant header does not match configured tenant",
            )
        return AuthContext(subject="development", tenant_id=tenant, roles=frozenset({"admin"}))

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required"
        )

    token = credentials.credentials
    client = _jwk_clients.setdefault(settings.oidc_jwks_url, PyJWKClient(settings.oidc_jwks_url))
    try:
        signing_key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)
        if not signing_key.algorithm_name:
            raise jwt.PyJWTError("Signing key has no algorithm")
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=[signing_key.algorithm_name],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "tenant_id"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

    tenant_id = str(claims["tenant_id"])
    if not 1 <= len(tenant_id) <= 128:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid tenant claim")
    roles_value = claims.get("roles", [])
    if isinstance(roles_value, str):
        roles = frozenset({roles_value})
    elif isinstance(roles_value, list) and all(isinstance(item, str) for item in roles_value):
        roles = frozenset(roles_value)
    else:
        roles = frozenset()
    return AuthContext(subject=str(claims["sub"]), tenant_id=tenant_id, roles=roles)


async def auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_tenant_id: str | None = Header(default=None),
) -> AuthContext:
    return await authenticate(credentials, x_tenant_id)


def require_role(context: AuthContext, role: str) -> None:
    if role not in context.roles and "admin" not in context.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
