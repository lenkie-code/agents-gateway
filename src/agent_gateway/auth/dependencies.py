"""FastAPI dependencies for authentication."""

from __future__ import annotations

from fastapi import HTTPException, Request

from agent_gateway.auth.domain import AuthResult


def get_auth(request: Request) -> AuthResult:
    """FastAPI dependency to extract auth context from ASGI scope.

    Usage::

        @router.get("/v1/agents")
        async def list_agents(auth: AuthResult = Depends(get_auth)):
            ...
    """
    auth: AuthResult | None = request.scope.get("auth")
    if auth is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return auth
