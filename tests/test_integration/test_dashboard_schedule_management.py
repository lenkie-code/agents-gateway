"""Tests for admin schedule management features."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from agent_gateway.gateway import Gateway

FIXTURE_WORKSPACE = Path(__file__).resolve().parent.parent / "fixtures" / "workspace"


def _copy_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    shutil.copytree(FIXTURE_WORKSPACE, ws)
    return ws


def _mock_repos(gw: Gateway) -> None:
    exec_repo = AsyncMock()
    exec_repo.list_all.return_value = []
    exec_repo.count_all.return_value = 0
    exec_repo.get_summary_stats.return_value = {
        "total_executions": 0,
        "total_cost_usd": 0.0,
        "success_count": 0,
        "avg_duration_ms": 0.0,
    }
    exec_repo.get_schedule_stats.return_value = {
        "total_scheduled": 0,
        "active_schedules": 0,
        "success": 0,
        "failed": 0,
        "running": 0,
    }

    schedule_repo = AsyncMock()
    schedule_repo.list_all.return_value = []
    schedule_repo.get.return_value = None

    user_agent_config_repo = AsyncMock()
    user_agent_config_repo.list_by_user.return_value = []

    user_schedule_repo = AsyncMock()
    user_schedule_repo.list_by_user.return_value = []

    gw._execution_repo = exec_repo  # type: ignore[assignment]
    gw._schedule_repo = schedule_repo  # type: ignore[assignment]
    gw._user_agent_config_repo = user_agent_config_repo  # type: ignore[assignment]
    gw._user_schedule_repo = user_schedule_repo  # type: ignore[assignment]


async def _make_gw(ws: Path) -> Gateway:
    gw = Gateway(workspace=str(ws), auth=False, title="Test")
    gw.use_dashboard(
        auth_password="testpass",
        auth_username="testuser",
        admin_username="admin",
        admin_password="adminpass",
    )
    return gw


async def _login(client: AsyncClient, username: str, password: str) -> None:
    await client.post(
        "/dashboard/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


class TestScheduleDetailPage:
    async def test_detail_page_403_for_non_admin(self, tmp_path: Path) -> None:
        """Non-admin user gets 403."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                await _login(client, "testuser", "testpass")
                resp = await client.get("/dashboard/schedules/some:schedule/detail")
                assert resp.status_code == 403


class TestScheduleEdit:
    async def test_edit_requires_admin(self, tmp_path: Path) -> None:
        """Non-admin user gets 403."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                await _login(client, "testuser", "testpass")
                resp = await client.post(
                    "/dashboard/schedules/some:schedule/edit",
                    data={
                        "cron_expr": "*/5 * * * *",
                        "message": "test",
                        "timezone": "UTC",
                    },
                    follow_redirects=False,
                )
                assert resp.status_code == 403
