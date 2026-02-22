"""Tests for CORS middleware integration."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agent_gateway.gateway import Gateway

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
FIXTURE_WORKSPACE = FIXTURES_DIR / "workspace"


def _make_gateway(*, cors_enabled: bool = True, **cors_kwargs: object) -> Gateway:
    gw = Gateway(workspace=str(FIXTURE_WORKSPACE), auth=False)
    if cors_enabled:
        gw.use_cors(**cors_kwargs)  # type: ignore[arg-type]
    return gw


@pytest.fixture
async def cors_client() -> AsyncClient:
    gw = _make_gateway()
    async with gw:
        transport = ASGITransport(app=gw)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac  # type: ignore[misc]


@pytest.fixture
async def restricted_cors_client() -> AsyncClient:
    gw = _make_gateway(allow_origins=["https://myapp.com"])
    async with gw:
        transport = ASGITransport(app=gw)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac  # type: ignore[misc]


class TestCorsPreflightRequests:
    async def test_preflight_returns_cors_headers(self, cors_client: AsyncClient) -> None:
        resp = await cors_client.options(
            "/v1/health",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "*"

    async def test_preflight_with_restricted_origin(
        self, restricted_cors_client: AsyncClient
    ) -> None:
        resp = await restricted_cors_client.options(
            "/v1/health",
            headers={
                "Origin": "https://myapp.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "https://myapp.com"

    async def test_preflight_disallowed_origin(self, restricted_cors_client: AsyncClient) -> None:
        resp = await restricted_cors_client.options(
            "/v1/health",
            headers={
                "Origin": "https://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in resp.headers


class TestCorsActualRequests:
    async def test_actual_request_includes_cors_headers(self, cors_client: AsyncClient) -> None:
        resp = await cors_client.get(
            "/v1/health",
            headers={"Origin": "https://example.com"},
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "*"

    async def test_max_age_header_on_preflight(self, cors_client: AsyncClient) -> None:
        resp = await cors_client.options(
            "/v1/health",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers["access-control-max-age"] == "3600"


class TestCorsDisabled:
    async def test_no_cors_headers_when_disabled(self) -> None:
        gw = _make_gateway(cors_enabled=False)
        async with gw:
            transport = ASGITransport(app=gw)  # type: ignore[arg-type]
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/v1/health",
                    headers={"Origin": "https://example.com"},
                )
                assert "access-control-allow-origin" not in resp.headers


class TestUseCorsApi:
    def test_use_cors_enables_cors(self) -> None:
        gw = Gateway(workspace=str(FIXTURE_WORKSPACE), auth=False)
        gw.use_cors(allow_origins=["https://myapp.com"])
        assert gw._pending_cors_config is not None
        assert gw._pending_cors_config.enabled is True
        assert gw._pending_cors_config.allow_origins == ["https://myapp.com"]

    def test_use_cors_returns_self(self) -> None:
        gw = Gateway(workspace=str(FIXTURE_WORKSPACE), auth=False)
        result = gw.use_cors()
        assert result is gw

    async def test_use_cors_after_start_raises(self) -> None:
        gw = Gateway(workspace=str(FIXTURE_WORKSPACE), auth=False)
        async with gw:
            with pytest.raises(RuntimeError, match="Cannot configure CORS"):
                gw.use_cors()
