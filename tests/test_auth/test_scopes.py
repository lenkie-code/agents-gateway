"""Tests for scope enforcement."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, FastAPI, Path

from agent_gateway.auth.domain import AuthResult
from agent_gateway.auth.scopes import RequireScope


def _build_app() -> FastAPI:
    """Build a minimal FastAPI app with scope-protected routes."""
    app = FastAPI()
    router = APIRouter(prefix="/v1")

    @router.get(
        "/agents",
        dependencies=[Depends(RequireScope("agents:read"))],
    )
    async def list_agents() -> dict[str, str]:
        return {"status": "ok"}

    @router.post(
        "/agents/{agent_id}/invoke",
        dependencies=[Depends(RequireScope("agents:invoke"))],
    )
    async def invoke_agent(agent_id: str = Path(...)) -> dict[str, str]:
        return {"agent_id": agent_id}

    @router.post(
        "/reload",
        dependencies=[Depends(RequireScope("admin"))],
    )
    async def reload() -> dict[str, str]:
        return {"status": "reloaded"}

    app.include_router(router)
    return app


def _make_client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    )


def _inject_auth(
    app: FastAPI,
    scopes: list[str],
    subject: str = "test-user",
) -> FastAPI:
    """Add middleware that injects auth context into scope."""
    original_app = app

    class _InjectAuth:
        def __init__(self, app: Any) -> None:
            self.app = app

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            if scope["type"] == "http":
                scope["auth"] = AuthResult.ok(subject=subject, scopes=scopes, method="test")
            await self.app(scope, receive, send)

    # Wrap the ASGI app
    wrapped = _InjectAuth(original_app)

    return wrapped  # type: ignore[return-value]


class TestRequireScope:
    async def test_wildcard_grants_all(self) -> None:
        app = _inject_auth(_build_app(), scopes=["*"])
        async with _make_client(app) as client:
            resp = await client.get("/v1/agents")
        assert resp.status_code == 200

    async def test_specific_scope_grants_access(self) -> None:
        app = _inject_auth(_build_app(), scopes=["agents:read"])
        async with _make_client(app) as client:
            resp = await client.get("/v1/agents")
        assert resp.status_code == 200

    async def test_missing_scope_returns_403(self) -> None:
        app = _inject_auth(_build_app(), scopes=["agents:read"])
        async with _make_client(app) as client:
            resp = await client.post("/v1/reload")
        assert resp.status_code == 403
        assert "admin" in resp.json()["detail"]

    async def test_agent_specific_scope(self) -> None:
        app = _inject_auth(_build_app(), scopes=["agents:invoke:underwriting"])
        async with _make_client(app) as client:
            resp = await client.post("/v1/agents/underwriting/invoke")
        assert resp.status_code == 200

    async def test_agent_specific_scope_wrong_agent(self) -> None:
        app = _inject_auth(_build_app(), scopes=["agents:invoke:underwriting"])
        async with _make_client(app) as client:
            resp = await client.post("/v1/agents/other-agent/invoke")
        assert resp.status_code == 403

    async def test_no_auth_context_passes_through(self) -> None:
        """When auth middleware is not active, RequireScope is a no-op."""
        app = _build_app()
        async with _make_client(app) as client:
            resp = await client.get("/v1/agents")
        assert resp.status_code == 200

    async def test_admin_scope(self) -> None:
        app = _inject_auth(_build_app(), scopes=["admin"])
        async with _make_client(app) as client:
            resp = await client.post("/v1/reload")
        assert resp.status_code == 200
