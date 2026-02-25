"""Unit tests for dashboard authentication (auth.py)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from agent_gateway.dashboard.auth import (
    DashboardUser,
    _hash_password,
    make_get_dashboard_user,
    make_login_handler,
    make_require_admin,
)

from .conftest import make_auth_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    *,
    session: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> Request:
    """Build a real Starlette Request with an in-scope session dict."""
    raw_headers: list[tuple[bytes, bytes]] = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode(), v.encode()))
    scope: dict[str, object] = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": raw_headers,
        "session": session if session is not None else {},
    }
    return Request(scope=scope)


# ---------------------------------------------------------------------------
# DashboardUser dataclass
# ---------------------------------------------------------------------------


class TestDashboardUser:
    def test_defaults(self) -> None:
        user = DashboardUser(username="alice")
        assert user.display_name == ""
        assert user.auth_method == "password"
        assert user.is_admin is False

    def test_custom_values(self) -> None:
        user = DashboardUser(
            username="bob",
            display_name="Bob",
            auth_method="oauth2",
            is_admin=True,
        )
        assert user.username == "bob"
        assert user.display_name == "Bob"
        assert user.auth_method == "oauth2"
        assert user.is_admin is True


# ---------------------------------------------------------------------------
# _hash_password
# ---------------------------------------------------------------------------


class TestHashPassword:
    def test_deterministic(self) -> None:
        assert _hash_password("secret") == _hash_password("secret")

    def test_returns_64_char_hex(self) -> None:
        h = _hash_password("anything")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_inputs_different_hashes(self) -> None:
        assert _hash_password("a") != _hash_password("b")


# ---------------------------------------------------------------------------
# make_get_dashboard_user
# ---------------------------------------------------------------------------


class TestGetDashboardUser:
    async def test_auth_disabled_returns_anonymous(self) -> None:
        cfg = make_auth_config(enabled=False)
        dep = make_get_dashboard_user(cfg)
        user = await dep(_make_request())
        assert user.username == "anonymous"

    async def test_no_session_raises_302(self) -> None:
        cfg = make_auth_config()
        dep = make_get_dashboard_user(cfg)
        with pytest.raises(HTTPException) as exc_info:
            await dep(_make_request(session={}))
        assert exc_info.value.status_code == 302
        assert exc_info.value.headers is not None
        assert exc_info.value.headers["Location"] == "/dashboard/login"

    async def test_no_session_htmx_raises_204(self) -> None:
        cfg = make_auth_config()
        dep = make_get_dashboard_user(cfg)
        req = _make_request(session={}, headers={"HX-Request": "true"})
        with pytest.raises(HTTPException) as exc_info:
            await dep(req)
        assert exc_info.value.status_code == 204
        assert exc_info.value.headers is not None
        assert exc_info.value.headers["HX-Redirect"] == "/dashboard/login"

    async def test_valid_session_returns_user(self) -> None:
        cfg = make_auth_config()
        dep = make_get_dashboard_user(cfg)
        user = await dep(_make_request(session={"dashboard_user": "testuser"}))
        assert user.username == "testuser"
        assert user.is_admin is False

    async def test_admin_user_detected(self) -> None:
        cfg = make_auth_config()
        dep = make_get_dashboard_user(cfg)
        user = await dep(_make_request(session={"dashboard_user": "admin"}))
        assert user.username == "admin"
        assert user.is_admin is True

    async def test_non_admin_user(self) -> None:
        cfg = make_auth_config()
        dep = make_get_dashboard_user(cfg)
        user = await dep(_make_request(session={"dashboard_user": "someone"}))
        assert user.is_admin is False


# ---------------------------------------------------------------------------
# make_require_admin
# ---------------------------------------------------------------------------


class TestRequireAdmin:
    async def test_admin_passes(self) -> None:
        cfg = make_auth_config()
        dep = make_require_admin(cfg)
        user = await dep(_make_request(session={"dashboard_user": "admin"}))
        assert user.is_admin is True

    async def test_non_admin_raises_403(self) -> None:
        cfg = make_auth_config()
        dep = make_require_admin(cfg)
        with pytest.raises(HTTPException) as exc_info:
            await dep(_make_request(session={"dashboard_user": "testuser"}))
        assert exc_info.value.status_code == 403

    async def test_non_admin_htmx_has_reswap_header(self) -> None:
        cfg = make_auth_config()
        dep = make_require_admin(cfg)
        req = _make_request(
            session={"dashboard_user": "testuser"},
            headers={"HX-Request": "true"},
        )
        with pytest.raises(HTTPException) as exc_info:
            await dep(req)
        assert exc_info.value.status_code == 403
        assert exc_info.value.headers is not None
        assert exc_info.value.headers["HX-Reswap"] == "none"


# ---------------------------------------------------------------------------
# make_login_handler
# ---------------------------------------------------------------------------


class TestLoginHandler:
    async def test_valid_credentials_redirects(self) -> None:
        cfg = make_auth_config()
        handler = make_login_handler(cfg)
        req = _make_request(session={})
        result = await handler(req, username="testuser", password="testpass")
        # Should be a RedirectResponse
        assert hasattr(result, "status_code") and result.status_code == 303
        assert req.session["dashboard_user"] == "testuser"

    async def test_valid_credentials_sets_csrf(self) -> None:
        cfg = make_auth_config()
        handler = make_login_handler(cfg)
        req = _make_request(session={})
        await handler(req, username="testuser", password="testpass")
        assert "csrf_token" in req.session
        assert len(req.session["csrf_token"]) == 64  # hex(32)

    async def test_invalid_password_returns_error(self) -> None:
        cfg = make_auth_config()
        handler = make_login_handler(cfg)
        req = _make_request(session={})
        result = await handler(req, username="testuser", password="wrong")
        assert isinstance(result, dict)
        assert "error" in result

    async def test_invalid_username_returns_error(self) -> None:
        cfg = make_auth_config()
        handler = make_login_handler(cfg)
        req = _make_request(session={})
        result = await handler(req, username="nobody", password="testpass")
        assert isinstance(result, dict)
        assert "error" in result

    async def test_admin_login(self) -> None:
        cfg = make_auth_config()
        handler = make_login_handler(cfg)
        req = _make_request(session={})
        result = await handler(req, username="admin", password="adminpass")
        assert hasattr(result, "status_code") and result.status_code == 303
        assert req.session["dashboard_user"] == "admin"

    async def test_admin_wrong_password_falls_through(self) -> None:
        cfg = make_auth_config()
        handler = make_login_handler(cfg)
        req = _make_request(session={})
        result = await handler(req, username="admin", password="wrong")
        assert isinstance(result, dict)
        assert "error" in result
