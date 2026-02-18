"""Scope-based authorization for API endpoints."""

from __future__ import annotations

from fastapi import HTTPException, Request

from agent_gateway.auth.domain import AuthResult


class RequireScope:
    """FastAPI dependency that checks caller scopes against required scopes.

    Supports:
    - ``*`` wildcard grants access to everything
    - Agent-specific scopes: ``agents:invoke:underwriting`` matches
      ``agents:invoke`` requirement when the route has matching ``agent_id``

    Usage::

        @router.post("/v1/agents/{agent_id}/invoke",
                      dependencies=[Depends(RequireScope("agents:invoke"))])
        async def invoke_agent(...): ...
    """

    def __init__(self, *required: str) -> None:
        self._required = set(required)

    async def __call__(self, request: Request) -> None:
        auth: AuthResult | None = request.scope.get("auth")
        if auth is None:
            # No auth context — middleware not active (auth disabled)
            return

        granted = set(auth.scopes)

        # Wildcard grants all scopes
        if "*" in granted:
            return

        # Check agent-specific scopes
        missing = set()
        for req in self._required:
            if req in granted:
                continue

            # Check for agent-specific match: agents:invoke:agent_id
            if req == "agents:invoke":
                agent_id = request.path_params.get("agent_id", "")
                if f"agents:invoke:{agent_id}" in granted:
                    continue

            missing.add(req)

        if missing:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient scopes. Missing: {sorted(missing)}",
            )
