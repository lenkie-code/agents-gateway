"""Tests for the pure ASGI auth middleware."""

from __future__ import annotations

import json
from typing import Any

import httpx

from agent_gateway.auth.domain import AuthResult
from agent_gateway.auth.middleware import AuthMiddleware


class _StubProvider:
    """Auth provider that accepts a specific token."""

    def __init__(self, valid_token: str = "valid-token") -> None:
        self._valid_token = valid_token

    async def authenticate(self, token: str) -> AuthResult:
        if token == self._valid_token:
            return AuthResult.ok(subject="test-user", scopes=["*"], method="api_key")
        return AuthResult.denied("Invalid token")

    async def close(self) -> None:
        pass


async def _echo_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """Minimal ASGI app that returns auth context as JSON."""
    auth = scope.get("auth")
    body_data: dict[str, Any] = {"path": scope["path"]}
    if auth is not None:
        body_data["auth"] = {
            "subject": auth.subject,
            "scopes": auth.scopes,
            "method": auth.auth_method,
        }
    body = json.dumps(body_data).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"application/json"]],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _build_client(
    valid_token: str = "valid-token",
    public_paths: frozenset[str] | None = None,
) -> httpx.AsyncClient:
    provider = _StubProvider(valid_token)
    app = AuthMiddleware(
        _echo_app,
        provider=provider,
        public_paths=public_paths or frozenset({"/v1/health"}),
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    )


class TestAuthMiddleware:
    async def test_valid_token(self) -> None:
        async with _build_client() as client:
            resp = await client.get(
                "/v1/agents",
                headers={"Authorization": "Bearer valid-token"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["auth"]["subject"] == "test-user"

    async def test_missing_auth_header(self) -> None:
        async with _build_client() as client:
            resp = await client.get("/v1/agents")
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "auth_required"

    async def test_invalid_token(self) -> None:
        async with _build_client() as client:
            resp = await client.get(
                "/v1/agents",
                headers={"Authorization": "Bearer bad-token"},
            )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "invalid_credentials"

    async def test_non_bearer_scheme(self) -> None:
        async with _build_client() as client:
            resp = await client.get(
                "/v1/agents",
                headers={"Authorization": "Basic dXNlcjpwYXNz"},
            )
        assert resp.status_code == 401

    async def test_public_path_bypasses_auth(self) -> None:
        async with _build_client() as client:
            resp = await client.get("/v1/health")
        assert resp.status_code == 200

    async def test_non_v1_path_bypasses_auth(self) -> None:
        async with _build_client() as client:
            resp = await client.get("/custom/route")
        assert resp.status_code == 200

    async def test_www_authenticate_header(self) -> None:
        async with _build_client() as client:
            resp = await client.get("/v1/agents")
        assert resp.headers.get("www-authenticate") == "Bearer"

    async def test_auth_context_stored_in_scope(self) -> None:
        async with _build_client() as client:
            resp = await client.get(
                "/v1/agents",
                headers={"Authorization": "Bearer valid-token"},
            )
        data = resp.json()
        assert data["auth"]["method"] == "api_key"
        assert data["auth"]["scopes"] == ["*"]
