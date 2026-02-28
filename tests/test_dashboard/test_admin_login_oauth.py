"""Integration tests for admin password login when OAuth2 is configured."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from agent_gateway.config import (
    DashboardAuthConfig,
    DashboardConfig,
    DashboardOAuth2Config,
)
from agent_gateway.dashboard.router import register_dashboard
from agent_gateway.gateway import Gateway

FIXTURE_WORKSPACE = Path(__file__).resolve().parent.parent / "fixtures" / "workspace"


def _mock_repos(gw: Gateway) -> None:
    """Replace persistence repos with async mocks returning empty defaults."""
    exec_repo = AsyncMock()
    exec_repo.list_all.return_value = []
    exec_repo.count_all.return_value = 0
    exec_repo.get.return_value = None
    exec_repo.get_with_steps.return_value = None
    exec_repo.list_conversations_summary.return_value = []
    exec_repo.count_conversations.return_value = 0
    exec_repo.get_summary_stats.return_value = {
        "total_executions": 0,
        "total_cost_usd": 0.0,
        "success_count": 0,
        "avg_duration_ms": 0.0,
    }
    exec_repo.cost_by_day.return_value = []
    exec_repo.executions_by_day.return_value = []
    exec_repo.cost_by_agent.return_value = []
    exec_repo.list_by_session.return_value = []
    exec_repo.get_schedule_stats.return_value = {
        "total_scheduled": 0,
        "active_schedules": 0,
        "success": 0,
        "failed": 0,
        "running": 0,
    }
    exec_repo.list_children.return_value = []
    exec_repo.cost_by_root_execution.return_value = 0.0

    schedule_repo = AsyncMock()
    schedule_repo.list_all.return_value = []
    schedule_repo.get.return_value = None

    user_agent_config_repo = AsyncMock()
    user_agent_config_repo.list_by_user.return_value = []
    user_agent_config_repo.get.return_value = None

    user_schedule_repo = AsyncMock()
    user_schedule_repo.list_by_user.return_value = []

    gw._execution_repo = exec_repo  # type: ignore[assignment]
    gw._schedule_repo = schedule_repo  # type: ignore[assignment]
    gw._user_agent_config_repo = user_agent_config_repo  # type: ignore[assignment]
    gw._user_schedule_repo = user_schedule_repo  # type: ignore[assignment]


def _make_oauth_gateway(
    *,
    admin_username: str | None = "admin",
    admin_password: str | None = "adminpass",
) -> Gateway:
    """Build a Gateway with OAuth2 dashboard and optional admin credentials."""
    gw = Gateway(workspace=str(FIXTURE_WORKSPACE), auth=False, title="Test")
    # Use password dashboard to set up session middleware (always needs admin creds)
    gw.use_dashboard(
        auth_username="user",
        auth_password="userpass",
        admin_username="admin",
        admin_password="adminpass",
    )
    # Build a DashboardConfig with the desired admin creds for the OAuth2 overlay
    auth_kwargs: dict[str, object] = {
        "enabled": True,
        "username": "user",
        "password": "userpass",
    }
    if admin_username is not None:
        auth_kwargs["admin_username"] = admin_username
    if admin_password is not None:
        auth_kwargs["admin_password"] = admin_password
    dash_config = DashboardConfig(auth=DashboardAuthConfig(**auth_kwargs))
    oauth2_config = DashboardOAuth2Config(
        issuer="https://idp.example.com",
        client_id="test-client",
        client_secret="test-secret",
    )
    discovery_client = AsyncMock()
    register_dashboard(
        gw, dash_config, oauth2_config=oauth2_config, discovery_client=discovery_client
    )
    return gw


async def _make_client(gw: Gateway) -> AsyncClient:
    transport = ASGITransport(app=gw)
    return AsyncClient(transport=transport, base_url="http://test")


class TestAdminLoginWithOAuth:
    async def test_login_page_shows_admin_form_when_oauth_with_admin_creds(self) -> None:
        gw = _make_oauth_gateway(admin_username="admin", admin_password="adminpass")
        async with gw:
            _mock_repos(gw)
            client = await _make_client(gw)
            async with client:
                resp = await client.get("/dashboard/login")
                assert resp.status_code == 200
                html = resp.text
                # SSO button present
                assert "Sign in with SSO" in html or "oauth2/authorize" in html
                # Admin form present inside details element
                assert "<details" in html
                assert "admin credentials" in html.lower()
                # Password input present
                assert 'name="password"' in html

    async def test_login_page_hides_admin_form_when_oauth_without_admin_creds(self) -> None:
        gw = _make_oauth_gateway(admin_username=None, admin_password=None)
        async with gw:
            _mock_repos(gw)
            client = await _make_client(gw)
            async with client:
                resp = await client.get("/dashboard/login")
                assert resp.status_code == 200
                html = resp.text
                # SSO button present
                assert "oauth2/authorize" in html
                # No admin form
                assert "<details" not in html
                assert 'name="password"' not in html

    async def test_admin_password_login_works_when_oauth_configured(self) -> None:
        gw = _make_oauth_gateway(admin_username="admin", admin_password="adminpass")
        async with gw:
            _mock_repos(gw)
            client = await _make_client(gw)
            async with client:
                resp = await client.post(
                    "/dashboard/login",
                    data={"username": "admin", "password": "adminpass"},
                    follow_redirects=False,
                )
                assert resp.status_code == 303
                assert "/dashboard/" in resp.headers.get("location", "")

    async def test_admin_password_login_rejects_bad_creds_when_oauth_configured(self) -> None:
        gw = _make_oauth_gateway(admin_username="admin", admin_password="adminpass")
        async with gw:
            _mock_repos(gw)
            client = await _make_client(gw)
            async with client:
                resp = await client.post(
                    "/dashboard/login",
                    data={"username": "admin", "password": "wrong"},
                    follow_redirects=False,
                )
                assert resp.status_code == 401
                html = resp.text
                assert "Invalid" in html
                # Details element should be open on error
                assert "<details open>" in html or "<details open " in html
