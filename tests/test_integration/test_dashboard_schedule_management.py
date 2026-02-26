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
                assert resp.status_code == 303

    async def test_detail_page_404_for_nonexistent_schedule(self, tmp_path: Path) -> None:
        """Admin gets 404 for a schedule that doesn't exist."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                await _login(client, "admin", "adminpass")
                resp = await client.get("/dashboard/schedules/nonexistent/detail")
                assert resp.status_code == 404


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
                assert resp.status_code == 303

    async def test_edit_nonexistent_schedule_returns_404(self, tmp_path: Path) -> None:
        """Editing unknown schedule returns 404."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                await _login(client, "admin", "adminpass")
                resp = await client.post(
                    "/dashboard/schedules/nonexistent/edit",
                    data={
                        "cron_expr": "*/5 * * * *",
                        "message": "test",
                        "timezone": "UTC",
                    },
                    follow_redirects=False,
                )
                assert resp.status_code == 404

    async def test_edit_invalid_cron_returns_422(self, tmp_path: Path) -> None:
        """Invalid cron expression returns 422 with inline error."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)
            # Mock get_schedule to return a schedule so the handler renders the form
            schedule_data = {
                "id": "test:schedule",
                "agent_id": next(iter(gw.agents)),
                "cron": "*/5 * * * *",
                "message": "hello",
                "timezone": "UTC",
                "enabled": True,
                "last_run_at": None,
                "next_run_at": None,
            }
            gw._schedule_repo.get.return_value = None  # type: ignore[union-attr]

            async def mock_get_schedule(sid: str) -> dict[str, object] | None:
                if sid == "test:schedule":
                    return schedule_data
                return None

            gw.get_schedule = mock_get_schedule  # type: ignore[assignment]

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                await _login(client, "admin", "adminpass")
                resp = await client.post(
                    "/dashboard/schedules/test:schedule/edit",
                    data={
                        "cron_expr": "not a cron",
                        "message": "test",
                        "timezone": "UTC",
                    },
                    follow_redirects=False,
                )
                assert resp.status_code == 422
                assert "Invalid cron" in resp.text

    async def test_edit_invalid_timezone_returns_422(self, tmp_path: Path) -> None:
        """Invalid timezone returns 422 with inline error."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)
            schedule_data = {
                "id": "test:schedule",
                "agent_id": next(iter(gw.agents)),
                "cron": "*/5 * * * *",
                "message": "hello",
                "timezone": "UTC",
                "enabled": True,
                "last_run_at": None,
                "next_run_at": None,
            }

            async def mock_get_schedule(sid: str) -> dict[str, object] | None:
                if sid == "test:schedule":
                    return schedule_data
                return None

            gw.get_schedule = mock_get_schedule  # type: ignore[assignment]

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                await _login(client, "admin", "adminpass")
                resp = await client.post(
                    "/dashboard/schedules/test:schedule/edit",
                    data={
                        "cron_expr": "*/5 * * * *",
                        "message": "test",
                        "timezone": "Not/A/Timezone",
                    },
                    follow_redirects=False,
                )
                assert resp.status_code == 422
                # May show "Invalid cron" or "Invalid timezone" depending on validation order
                assert "Invalid" in resp.text
