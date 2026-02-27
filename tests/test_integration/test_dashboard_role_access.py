"""Tests for role-based dashboard page access restrictions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from agent_gateway.exceptions import ConfigError
from agent_gateway.gateway import Gateway
from agent_gateway.persistence.backends.sql.repository import ExecutionRepository
from agent_gateway.persistence.backends.sqlite import SqliteBackend
from agent_gateway.persistence.domain import ExecutionRecord

FIXTURE_WORKSPACE = Path(__file__).resolve().parent.parent / "fixtures" / "workspace"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_repos(gw: Gateway) -> None:
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


async def _make_client(gw: Gateway) -> AsyncClient:
    transport = ASGITransport(app=gw)
    return AsyncClient(transport=transport, base_url="http://test")


async def _login(client: AsyncClient, username: str, password: str) -> None:
    await client.post(
        "/dashboard/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def _make_gw() -> Gateway:
    gw = Gateway(workspace=str(FIXTURE_WORKSPACE), auth=False, title="Test")
    gw.use_dashboard(
        auth_password="testpass",
        auth_username="testuser",
        admin_username="admin",
        admin_password="adminpass",
    )
    return gw


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAdminCanAccessAnalytics:
    async def test_admin_analytics_200(self) -> None:
        gw = _make_gw()
        async with gw:
            _mock_repos(gw)
            client = await _make_client(gw)
            async with client:
                await _login(client, "admin", "adminpass")
                resp = await client.get("/dashboard/analytics")
                assert resp.status_code == 200


class TestNonAdminRedirectedFromAnalytics:
    async def test_non_admin_analytics_303(self) -> None:
        gw = _make_gw()
        async with gw:
            _mock_repos(gw)
            client = await _make_client(gw)
            async with client:
                await _login(client, "testuser", "testpass")
                resp = await client.get("/dashboard/analytics", follow_redirects=False)
                assert resp.status_code == 303
                assert "/dashboard/agents" in resp.headers.get("location", "")


class TestAdminCanAccessExecutions:
    async def test_admin_executions_200(self) -> None:
        gw = _make_gw()
        async with gw:
            _mock_repos(gw)
            client = await _make_client(gw)
            async with client:
                await _login(client, "admin", "adminpass")
                resp = await client.get("/dashboard/executions")
                assert resp.status_code == 200


class TestNonAdminRedirectedFromExecutions:
    async def test_non_admin_executions_303(self) -> None:
        gw = _make_gw()
        async with gw:
            _mock_repos(gw)
            client = await _make_client(gw)
            async with client:
                await _login(client, "testuser", "testpass")
                resp = await client.get("/dashboard/executions", follow_redirects=False)
                assert resp.status_code == 303
                assert "/dashboard/agents" in resp.headers.get("location", "")


class TestNonAdminRedirectedFromExecutionDetail:
    async def test_non_admin_execution_detail_303(self) -> None:
        gw = _make_gw()
        async with gw:
            _mock_repos(gw)
            client = await _make_client(gw)
            async with client:
                await _login(client, "testuser", "testpass")
                resp = await client.get("/dashboard/executions/some-id", follow_redirects=False)
                assert resp.status_code == 303


class TestHtmxNonAdminGets403:
    async def test_htmx_admin_page_403(self) -> None:
        gw = _make_gw()
        async with gw:
            _mock_repos(gw)
            client = await _make_client(gw)
            async with client:
                await _login(client, "testuser", "testpass")
                resp = await client.get(
                    "/dashboard/analytics",
                    headers={"HX-Request": "true"},
                    follow_redirects=False,
                )
                assert resp.status_code == 403
                assert resp.headers.get("HX-Reswap") == "none"


class TestConversationsUserScoping:
    """Conversations are filtered by user_id for non-admin users."""

    @pytest.fixture
    async def sqlite_backend(self, tmp_path):  # type: ignore[no-untyped-def]
        db_path = tmp_path / "test_role.db"
        backend = SqliteBackend(path=str(db_path))
        await backend.initialize()
        yield backend
        await backend.dispose()

    @pytest.fixture
    async def repo(self, sqlite_backend: SqliteBackend) -> ExecutionRepository:
        return ExecutionRepository(sqlite_backend._session_factory)

    @pytest.fixture
    async def seeded_repo(self, repo: ExecutionRepository) -> ExecutionRepository:
        now = datetime.now(UTC)
        records = (
            [
                ExecutionRecord(
                    id=f"exec-user-a-{i}",
                    agent_id="agent-a",
                    status="completed",
                    message=f"User A exec {i}",
                    session_id=f"session-a-{i}",
                    user_id="testuser",
                    created_at=now - timedelta(hours=i),
                    usage={"cost_usd": 0.01, "input_tokens": 10, "output_tokens": 5},
                )
                for i in range(10)
            ]
            + [
                ExecutionRecord(
                    id=f"exec-user-b-{i}",
                    agent_id="agent-a",
                    status="completed",
                    message=f"User B exec {i}",
                    session_id=f"session-b-{i}",
                    user_id="otheruser",
                    created_at=now - timedelta(hours=i),
                    usage={"cost_usd": 0.01, "input_tokens": 10, "output_tokens": 5},
                )
                for i in range(5)
            ]
            + [
                ExecutionRecord(
                    id="exec-no-user",
                    agent_id="agent-a",
                    status="completed",
                    message="No user (scheduler)",
                    session_id="session-nul",
                    user_id=None,
                    created_at=now - timedelta(hours=1),
                    usage={"cost_usd": 0.01, "input_tokens": 10, "output_tokens": 5},
                ),
            ]
        )
        for r in records:
            await repo.create(r)
        return repo

    async def test_non_admin_sees_only_own_conversations(
        self, seeded_repo: ExecutionRepository
    ) -> None:
        rows = await seeded_repo.list_conversations_summary(user_id="testuser")
        session_ids = {r["session_id"] for r in rows}
        assert all(s.startswith("session-a") for s in session_ids)
        assert len(session_ids) == 10

    async def test_admin_sees_all_conversations(self, seeded_repo: ExecutionRepository) -> None:
        rows = await seeded_repo.list_conversations_summary(user_id=None)
        assert len(rows) == 16  # 10 + 5 + 1

    async def test_non_admin_cannot_view_other_user_conversation(
        self, seeded_repo: ExecutionRepository
    ) -> None:
        """Non-admin user_id filter excludes NULL user_id rows."""
        rows = await seeded_repo.list_conversations_summary(user_id="testuser")
        session_ids = {r["session_id"] for r in rows}
        assert "session-nul" not in session_ids
        assert "session-b-0" not in session_ids

    async def test_count_conversations_user_scoped(self, seeded_repo: ExecutionRepository) -> None:
        count_a = await seeded_repo.count_conversations(user_id="testuser")
        assert count_a == 10

        count_b = await seeded_repo.count_conversations(user_id="otheruser")
        assert count_b == 5

        count_all = await seeded_repo.count_conversations(user_id=None)
        assert count_all == 16

    async def test_pagination_total_pages_user_scoped(
        self, seeded_repo: ExecutionRepository
    ) -> None:
        """Non-admin pagination reflects only their own conversations."""
        page_size = 5
        count_a = await seeded_repo.count_conversations(user_id="testuser")
        total_pages_a = max(1, (count_a + page_size - 1) // page_size)
        assert total_pages_a == 2

        count_b = await seeded_repo.count_conversations(user_id="otheruser")
        total_pages_b = max(1, (count_b + page_size - 1) // page_size)
        assert total_pages_b == 1


class TestStartupEnforcement:
    async def test_startup_fails_without_admin_credentials(self) -> None:
        gw = Gateway(workspace=str(FIXTURE_WORKSPACE), auth=False, title="Test")
        gw.use_dashboard(auth_password="testpass", auth_username="testuser")
        with pytest.raises(ConfigError, match="admin_username and admin_password"):
            async with gw:
                pass

    async def test_startup_succeeds_with_oauth2_no_admin_creds(self) -> None:
        gw = Gateway(workspace=str(FIXTURE_WORKSPACE), auth=False, title="Test")
        gw.use_dashboard(
            oauth2_issuer="https://example.com",
            oauth2_client_id="test-client",
            oauth2_client_secret="test-secret",
        )
        # Should not raise — OAuth2 does not require admin_username/admin_password
        async with gw:
            pass
