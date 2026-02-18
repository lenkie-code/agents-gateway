"""Integration tests for auth with the full Gateway."""

from __future__ import annotations

import httpx

from agent_gateway import Gateway


class TestGatewayAuthIntegration:
    """Test auth wiring through the Gateway lifecycle."""

    async def test_auth_disabled(self) -> None:
        """Gateway(auth=False) allows unauthenticated access."""
        gw = Gateway(auth=False)
        async with (
            gw,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=gw),  # type: ignore[arg-type]
                base_url="http://test",
            ) as client,
        ):
            resp = await client.get("/v1/health")
            assert resp.status_code == 200

    async def test_api_key_auth_via_fluent_api(self) -> None:
        """use_api_keys() enables API key authentication."""
        gw = Gateway(auth=True)
        gw.use_api_keys(
            [
                {"name": "test", "key": "my-secret-key", "scopes": ["*"]},
            ]
        )

        async with (
            gw,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=gw),  # type: ignore[arg-type]
                base_url="http://test",
            ) as client,
        ):
            # Without key — should fail
            resp = await client.get("/v1/agents")
            assert resp.status_code == 401

            # With valid key — should pass
            resp = await client.get(
                "/v1/agents",
                headers={"Authorization": "Bearer my-secret-key"},
            )
            assert resp.status_code == 200

            # Health endpoint — always public
            resp = await client.get("/v1/health")
            assert resp.status_code == 200

    async def test_use_api_keys_after_start_raises(self) -> None:
        """Cannot configure auth after gateway has started."""
        import pytest

        gw = Gateway(auth=False)
        gw._started = True
        with pytest.raises(RuntimeError, match="after gateway has started"):
            gw.use_api_keys([{"name": "k", "key": "v"}])

    async def test_use_oauth2_after_start_raises(self) -> None:
        import pytest

        gw = Gateway(auth=False)
        gw._started = True
        with pytest.raises(RuntimeError, match="after gateway has started"):
            gw.use_oauth2(issuer="https://a.com", audience="b")

    async def test_use_auth_none_disables(self) -> None:
        """use_auth(None) explicitly disables auth."""
        gw = Gateway(auth=True)
        gw.use_auth(None)
        # use_auth(None) sets _auth_provider to None (not the sentinel)
        assert gw._auth_provider is None

    async def test_custom_callable_auth(self) -> None:
        """Gateway(auth=my_fn) wraps a callable as an auth provider."""
        from agent_gateway.auth.domain import AuthResult

        async def my_auth(token: str) -> AuthResult:
            if token == "magic":
                return AuthResult.ok(subject="wizard", scopes=["*"], method="custom")
            return AuthResult.denied("nope")

        gw = Gateway(auth=my_auth)
        gw.use_sqlite(":memory:")

        async with (
            gw,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=gw),  # type: ignore[arg-type]
                base_url="http://test",
            ) as client,
        ):
            resp = await client.get(
                "/v1/agents",
                headers={"Authorization": "Bearer magic"},
            )
            assert resp.status_code == 200

            resp = await client.get(
                "/v1/agents",
                headers={"Authorization": "Bearer wrong"},
            )
            assert resp.status_code == 401

    async def test_scope_enforcement_via_api(self) -> None:
        """API keys with limited scopes are enforced."""
        gw = Gateway(auth=True)
        gw.use_api_keys(
            [
                {"name": "readonly", "key": "read-key", "scopes": ["agents:read"]},
            ]
        )

        async with (
            gw,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=gw),  # type: ignore[arg-type]
                base_url="http://test",
            ) as client,
        ):
            # agents:read scope — list agents should work
            resp = await client.get(
                "/v1/agents",
                headers={"Authorization": "Bearer read-key"},
            )
            assert resp.status_code == 200

            # agents:read scope — reload requires admin — should fail with 403
            resp = await client.post(
                "/v1/reload",
                headers={"Authorization": "Bearer read-key"},
            )
            assert resp.status_code == 403
