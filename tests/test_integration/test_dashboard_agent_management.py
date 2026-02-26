"""Tests for admin agent management features."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from agent_gateway.gateway import Gateway

FIXTURE_WORKSPACE = Path(__file__).resolve().parent.parent / "fixtures" / "workspace"


def _copy_workspace(tmp_path: Path) -> Path:
    """Copy fixture workspace so we can write to AGENT.md safely."""
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


def _read_frontmatter(agent_dir: Path) -> dict:
    import frontmatter

    post = frontmatter.loads((agent_dir / "AGENT.md").read_text(encoding="utf-8"))
    return dict(post.metadata)


class TestAgentDisable:
    async def test_disable_agent_blocks_invoke(self, tmp_path: Path) -> None:
        """Disabled agent returns 503 from /v1/agents/{id}/invoke."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)
            # Get the first agent
            agent_id = next(iter(gw.agents))
            agent = gw.agents[agent_id]
            # Write enabled: false directly
            from agent_gateway.workspace.writer import update_agent_frontmatter

            update_agent_frontmatter(agent.path, {"enabled": False})
            await gw.reload()

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/v1/agents/{agent_id}/invoke",
                    json={"message": "hello"},
                )
                assert resp.status_code == 503
                assert "disabled" in resp.json()["error"]["code"]

    async def test_disable_agent_blocks_chat(self, tmp_path: Path) -> None:
        """Disabled agent returns 503 from /v1/agents/{id}/chat."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)
            agent_id = next(iter(gw.agents))
            agent = gw.agents[agent_id]
            from agent_gateway.workspace.writer import update_agent_frontmatter

            update_agent_frontmatter(agent.path, {"enabled": False})
            await gw.reload()

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                resp = await client.post(
                    f"/v1/agents/{agent_id}/chat",
                    json={"message": "hello"},
                )
                assert resp.status_code == 503
                assert "disabled" in resp.json()["error"]["code"]

    async def test_introspection_shows_enabled_field(self, tmp_path: Path) -> None:
        """GET /v1/agents/{id} includes enabled field."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)
            agent_id = next(iter(gw.agents))

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                resp = await client.get(f"/v1/agents/{agent_id}")
                assert resp.status_code == 200
                data = resp.json()
                assert "enabled" in data
                assert data["enabled"] is True


class TestAgentToggle:
    async def test_toggle_writes_enabled_false_to_frontmatter(self, tmp_path: Path) -> None:
        """Toggle on enabled agent writes enabled: false to AGENT.md."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)
            agent_id = next(iter(gw.agents))
            agent = gw.agents[agent_id]

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                await _login(client, "admin", "adminpass")
                resp = await client.post(
                    f"/dashboard/agents/{agent_id}/toggle",
                    follow_redirects=False,
                )
                assert resp.status_code == 303

            meta = _read_frontmatter(agent.path)
            assert meta.get("enabled") is False

    async def test_toggle_requires_admin(self, tmp_path: Path) -> None:
        """Non-admin user gets 403."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)
            agent_id = next(iter(gw.agents))

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                await _login(client, "testuser", "testpass")
                resp = await client.post(
                    f"/dashboard/agents/{agent_id}/toggle",
                    follow_redirects=False,
                )
                assert resp.status_code == 303


class TestAgentDetailPage:
    async def test_detail_page_renders_for_admin(self, tmp_path: Path) -> None:
        """GET /dashboard/agents/{id}/detail returns 200 with agent data."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)
            agent_id = next(iter(gw.agents))

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                await _login(client, "admin", "adminpass")
                resp = await client.get(f"/dashboard/agents/{agent_id}/detail")
                assert resp.status_code == 200
                assert "text/html" in resp.headers["content-type"]

    async def test_detail_page_403_for_non_admin(self, tmp_path: Path) -> None:
        """Non-admin user gets 403."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)
            agent_id = next(iter(gw.agents))

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                await _login(client, "testuser", "testpass")
                resp = await client.get(f"/dashboard/agents/{agent_id}/detail")
                assert resp.status_code == 303


class TestAgentEdit:
    async def test_edit_updates_frontmatter_on_disk(self, tmp_path: Path) -> None:
        """POST /dashboard/agents/{id}/edit writes to AGENT.md."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)
            agent_id = next(iter(gw.agents))
            agent = gw.agents[agent_id]

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                await _login(client, "admin", "adminpass")
                resp = await client.post(
                    f"/dashboard/agents/{agent_id}/edit",
                    data={
                        "description": "Updated description",
                        "display_name": "Updated Name",
                        "tags": "tag1, tag2",
                        "model_name": "",
                        "model_temperature": "",
                        "model_max_tokens": "",
                        "execution_mode": "sync",
                    },
                    follow_redirects=False,
                )
                assert resp.status_code == 303

            meta = _read_frontmatter(agent.path)
            assert meta["description"] == "Updated description"

    async def test_edit_requires_admin(self, tmp_path: Path) -> None:
        """Non-admin user gets 403."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)
            agent_id = next(iter(gw.agents))

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                await _login(client, "testuser", "testpass")
                resp = await client.post(
                    f"/dashboard/agents/{agent_id}/edit",
                    data={"description": "x"},
                    follow_redirects=False,
                )
                assert resp.status_code == 303

    async def test_edit_nonexistent_agent_returns_404(self, tmp_path: Path) -> None:
        """Editing unknown agent returns 404."""
        ws = _copy_workspace(tmp_path)
        gw = await _make_gw(ws)
        async with gw:
            _mock_repos(gw)

            async with AsyncClient(
                transport=ASGITransport(app=gw), base_url="http://test"
            ) as client:
                await _login(client, "admin", "adminpass")
                resp = await client.post(
                    "/dashboard/agents/nonexistent/edit",
                    data={"description": "x"},
                    follow_redirects=False,
                )
                assert resp.status_code == 404
