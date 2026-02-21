"""Tests for dashboard OAuth2/OIDC login flow."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa as crypto_rsa

from agent_gateway.config import DashboardOAuth2Config
from agent_gateway.dashboard.oauth2 import (
    OIDCDiscoveryClient,
    make_authorize_handler,
    make_callback_handler,
)


def _make_config(**overrides: object) -> DashboardOAuth2Config:
    defaults = {
        "issuer": "https://auth.example.com",
        "client_id": "my-client",
        "client_secret": "my-secret",
        "scopes": ["openid", "profile", "email"],
    }
    defaults.update(overrides)
    return DashboardOAuth2Config(**defaults)


_DISCOVERY_DOC = {
    "issuer": "https://auth.example.com",
    "authorization_endpoint": "https://auth.example.com/authorize",
    "token_endpoint": "https://auth.example.com/token",
    "userinfo_endpoint": "https://auth.example.com/userinfo",
    "jwks_uri": "https://auth.example.com/.well-known/jwks.json",
}


def _generate_rsa_key():
    return crypto_rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _make_jwks(private_key, kid: str = "test-kid"):
    from jwt.algorithms import RSAAlgorithm

    pub_key = private_key.public_key()
    jwk_dict = json.loads(RSAAlgorithm.to_jwk(pub_key))
    jwk_dict["kid"] = kid
    jwk_dict["use"] = "sig"
    jwk_dict["alg"] = "RS256"
    return {"keys": [jwk_dict]}


def _make_id_token(private_key, kid: str = "test-kid", **claim_overrides):
    now = int(time.time())
    claims = {
        "iss": "https://auth.example.com",
        "sub": "user-123",
        "aud": "my-client",
        "exp": now + 3600,
        "iat": now,
        "email": "user@example.com",
        "name": "Test User",
    }
    claims.update(claim_overrides)
    return pyjwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def _mock_request(session: dict | None = None, query_params: dict | None = None):
    req = MagicMock()
    req.session = session if session is not None else {}
    req.query_params = query_params or {}
    req.url_for = MagicMock(return_value="http://localhost/dashboard/oauth2/callback")
    return req


class TestOIDCDiscoveryClient:
    async def test_discover_fetches_and_caches(self) -> None:
        client = OIDCDiscoveryClient("https://auth.example.com")
        mock_resp = MagicMock()
        mock_resp.json.return_value = _DISCOVERY_DOC
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.discover()
            assert result["authorization_endpoint"] == "https://auth.example.com/authorize"

            # Second call should use cache (no additional HTTP call)
            result2 = await client.discover()
            assert result2 == result
            assert client._http.get.call_count == 1

        await client.close()

    async def test_fetch_jwks_and_caches(self) -> None:
        client = OIDCDiscoveryClient("https://auth.example.com")
        jwks = {"keys": [{"kid": "k1", "kty": "RSA"}]}
        mock_resp = MagicMock()
        mock_resp.json.return_value = jwks
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.fetch_jwks("https://auth.example.com/.well-known/jwks.json")
            assert result["keys"][0]["kid"] == "k1"

            # Cached
            result2 = await client.fetch_jwks("https://auth.example.com/.well-known/jwks.json")
            assert result2 == result
            assert client._http.get.call_count == 1

        await client.close()


class TestAuthorizeHandler:
    async def test_generates_state_and_redirects(self) -> None:
        config = _make_config()
        discovery = OIDCDiscoveryClient("https://auth.example.com")

        with patch.object(
            discovery, "discover", new_callable=AsyncMock, return_value=_DISCOVERY_DOC
        ):
            handler = make_authorize_handler(config, discovery)
            req = _mock_request()
            resp = await handler(req)

            assert resp.status_code == 303
            assert "oauth2_state" in req.session
            assert len(req.session["oauth2_state"]) == 64  # 32 bytes hex
            location = resp.headers["location"]
            assert "auth.example.com/authorize" in location
            assert "response_type=code" in location
            assert "client_id=my-client" in location

        await discovery.close()

    async def test_discovery_failure_redirects_with_error(self) -> None:
        config = _make_config()
        discovery = OIDCDiscoveryClient("https://auth.example.com")

        with patch.object(
            discovery, "discover", new_callable=AsyncMock, side_effect=httpx.ConnectError("fail")
        ):
            handler = make_authorize_handler(config, discovery)
            req = _mock_request()
            resp = await handler(req)

            assert resp.status_code == 303
            assert "error=" in resp.headers["location"]

        await discovery.close()


class TestCallbackHandler:
    async def test_successful_callback(self) -> None:
        config = _make_config()
        discovery = OIDCDiscoveryClient("https://auth.example.com")
        private_key = _generate_rsa_key()
        jwks = _make_jwks(private_key)
        id_token = _make_id_token(private_key)

        token_response = httpx.Response(
            200,
            json={"id_token": id_token, "access_token": "at-123"},
            request=httpx.Request("POST", "https://auth.example.com/token"),
        )

        with (
            patch.object(
                discovery, "discover", new_callable=AsyncMock, return_value=_DISCOVERY_DOC
            ),
            patch.object(discovery, "fetch_jwks", new_callable=AsyncMock, return_value=jwks),
            patch("agent_gateway.dashboard.oauth2.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = token_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            handler = make_callback_handler(config, discovery)
            session = {"oauth2_state": "test-state-123"}
            req = _mock_request(
                session=session,
                query_params={"state": "test-state-123", "code": "auth-code-456"},
            )
            resp = await handler(req)

            assert resp.status_code == 303
            assert resp.headers["location"] == "/dashboard/"
            assert req.session["dashboard_user"] == "user@example.com"
            assert req.session["display_name"] == "Test User"
            assert req.session["auth_method"] == "oauth2"
            # State should be consumed
            assert "oauth2_state" not in req.session

        await discovery.close()

    async def test_state_mismatch_rejects(self) -> None:
        config = _make_config()
        discovery = OIDCDiscoveryClient("https://auth.example.com")

        handler = make_callback_handler(config, discovery)
        session = {"oauth2_state": "correct-state"}
        req = _mock_request(
            session=session,
            query_params={"state": "wrong-state", "code": "auth-code"},
        )
        resp = await handler(req)

        assert resp.status_code == 303
        assert "error=" in resp.headers["location"]

        await discovery.close()

    async def test_missing_state_rejects(self) -> None:
        config = _make_config()
        discovery = OIDCDiscoveryClient("https://auth.example.com")

        handler = make_callback_handler(config, discovery)
        req = _mock_request(
            session={},
            query_params={"code": "auth-code"},
        )
        resp = await handler(req)

        assert resp.status_code == 303
        assert "error=" in resp.headers["location"]

        await discovery.close()

    async def test_invalid_jwt_rejects(self) -> None:
        config = _make_config()
        discovery = OIDCDiscoveryClient("https://auth.example.com")

        # Create a token signed with one key but JWKS has a different key
        private_key1 = _generate_rsa_key()
        private_key2 = _generate_rsa_key()
        jwks = _make_jwks(private_key2)  # different key
        id_token = _make_id_token(private_key1)

        token_response = httpx.Response(
            200,
            json={"id_token": id_token, "access_token": "at-123"},
            request=httpx.Request("POST", "https://auth.example.com/token"),
        )

        with (
            patch.object(
                discovery, "discover", new_callable=AsyncMock, return_value=_DISCOVERY_DOC
            ),
            patch.object(discovery, "fetch_jwks", new_callable=AsyncMock, return_value=jwks),
            patch("agent_gateway.dashboard.oauth2.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = token_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            handler = make_callback_handler(config, discovery)
            session = {"oauth2_state": "test-state"}
            req = _mock_request(
                session=session,
                query_params={"state": "test-state", "code": "auth-code"},
            )
            resp = await handler(req)

            assert resp.status_code == 303
            assert "error=" in resp.headers["location"]

        await discovery.close()

    async def test_expired_token_rejects(self) -> None:
        config = _make_config()
        discovery = OIDCDiscoveryClient("https://auth.example.com")
        private_key = _generate_rsa_key()
        jwks = _make_jwks(private_key)
        id_token = _make_id_token(private_key, exp=int(time.time()) - 3600)

        token_response = httpx.Response(
            200,
            json={"id_token": id_token, "access_token": "at-123"},
            request=httpx.Request("POST", "https://auth.example.com/token"),
        )

        with (
            patch.object(
                discovery, "discover", new_callable=AsyncMock, return_value=_DISCOVERY_DOC
            ),
            patch.object(discovery, "fetch_jwks", new_callable=AsyncMock, return_value=jwks),
            patch("agent_gateway.dashboard.oauth2.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = token_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            handler = make_callback_handler(config, discovery)
            session = {"oauth2_state": "test-state"}
            req = _mock_request(
                session=session,
                query_params={"state": "test-state", "code": "auth-code"},
            )
            resp = await handler(req)

            assert resp.status_code == 303
            assert "error=" in resp.headers["location"]
            assert "expired" in resp.headers["location"].lower()

        await discovery.close()


class TestStartupValidation:
    def test_rejects_both_password_and_oauth2(self) -> None:
        from agent_gateway.config import (
            DashboardAuthConfig,
            DashboardConfig,
            DashboardOAuth2Config,
        )
        from agent_gateway.exceptions import ConfigError

        auth = DashboardAuthConfig(
            password="secret",
            oauth2=DashboardOAuth2Config(
                issuer="https://auth.example.com",
                client_id="cid",
                client_secret="csec",
            ),
        )
        dash_config = DashboardConfig(enabled=True, auth=auth)

        from agent_gateway.config import GatewayConfig

        gw_config = GatewayConfig(dashboard=dash_config)

        from agent_gateway.gateway import Gateway

        gw = Gateway(workspace="/tmp/nonexistent", auth=False)
        gw._config = gw_config

        with pytest.raises(ConfigError, match="mutually exclusive"):
            gw._maybe_init_dashboard()

    def test_rejects_oauth2_without_client_secret(self) -> None:
        from agent_gateway.config import (
            DashboardAuthConfig,
            DashboardConfig,
            DashboardOAuth2Config,
        )
        from agent_gateway.exceptions import ConfigError

        auth = DashboardAuthConfig(
            password="",
            oauth2=DashboardOAuth2Config(
                issuer="https://auth.example.com",
                client_id="cid",
                client_secret="",
            ),
        )
        dash_config = DashboardConfig(enabled=True, auth=auth)

        from agent_gateway.config import GatewayConfig

        gw_config = GatewayConfig(dashboard=dash_config)

        from agent_gateway.gateway import Gateway

        gw = Gateway(workspace="/tmp/nonexistent", auth=False)
        gw._config = gw_config

        with pytest.raises(ConfigError, match="client_secret"):
            gw._maybe_init_dashboard()
