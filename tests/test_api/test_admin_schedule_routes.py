"""Unit tests for admin schedule API routes (POST /v1/schedules, DELETE /v1/schedules/{id})."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from agent_gateway.exceptions import ScheduleConflictError, ScheduleValidationError
from agent_gateway.gateway import Gateway


def _write_workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace with one agent and persistence disabled."""
    (tmp_path / "gateway.yaml").write_text("persistence:\n  enabled: false\n")
    agents = tmp_path / "agents"
    agents.mkdir()
    (tmp_path / "skills").mkdir()
    (tmp_path / "tools").mkdir()

    agent_dir = agents / "test-agent"
    agent_dir.mkdir()
    (agent_dir / "AGENT.md").write_text("# Test Agent\n\nYou help with testing.\n")
    return tmp_path


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return _write_workspace(tmp_path)


def _mock_scheduler() -> MagicMock:
    """Return a non-None mock to satisfy the `gw.scheduler is not None` guard.

    Uses AsyncMock for stop() so that gateway shutdown doesn't raise.
    """
    mock = MagicMock()
    mock.stop = AsyncMock()
    return mock


# ---------------------------------------------------------------------------
# POST /v1/schedules — create admin schedule
# ---------------------------------------------------------------------------

_VALID_PAYLOAD = {
    "agent_id": "test-agent",
    "name": "daily-report",
    "cron_expr": "0 9 * * *",
    "message": "Generate the daily report",
}


async def test_create_schedule_201(workspace: Path) -> None:
    """Happy path: valid payload returns 201 with schedule_id."""
    gw = Gateway(workspace=str(workspace), auth=False)
    async with gw:
        gw._scheduler = _mock_scheduler()
        gw.create_admin_schedule = AsyncMock(return_value="admin:test-agent:daily-report")  # type: ignore[method-assign]

        async with AsyncClient(
            transport=ASGITransport(app=gw),
            base_url="http://test",  # type: ignore[arg-type]
        ) as ac:
            resp = await ac.post("/v1/schedules", json=_VALID_PAYLOAD)

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "created"
    assert body["schedule_id"] == "admin:test-agent:daily-report"


async def test_create_schedule_400_bad_cron(workspace: Path) -> None:
    """ScheduleValidationError from gateway returns 400."""
    gw = Gateway(workspace=str(workspace), auth=False)
    async with gw:
        gw._scheduler = _mock_scheduler()
        gw.create_admin_schedule = AsyncMock(  # type: ignore[method-assign]
            side_effect=ScheduleValidationError("Invalid cron expression")
        )

        async with AsyncClient(
            transport=ASGITransport(app=gw),
            base_url="http://test",  # type: ignore[arg-type]
        ) as ac:
            resp = await ac.post("/v1/schedules", json=_VALID_PAYLOAD)

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "schedule_validation_error"


async def test_create_schedule_409_duplicate(workspace: Path) -> None:
    """ScheduleConflictError from gateway returns 409."""
    gw = Gateway(workspace=str(workspace), auth=False)
    async with gw:
        gw._scheduler = _mock_scheduler()
        gw.create_admin_schedule = AsyncMock(  # type: ignore[method-assign]
            side_effect=ScheduleConflictError("Schedule already exists")
        )

        async with AsyncClient(
            transport=ASGITransport(app=gw),
            base_url="http://test",  # type: ignore[arg-type]
        ) as ac:
            resp = await ac.post("/v1/schedules", json=_VALID_PAYLOAD)

    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "schedule_conflict"


async def test_create_schedule_404_unknown_agent(workspace: Path) -> None:
    """Unknown agent_id returns 404."""
    gw = Gateway(workspace=str(workspace), auth=False)
    async with gw:
        gw._scheduler = _mock_scheduler()

        payload = {**_VALID_PAYLOAD, "agent_id": "nonexistent"}
        async with AsyncClient(
            transport=ASGITransport(app=gw),
            base_url="http://test",  # type: ignore[arg-type]
        ) as ac:
            resp = await ac.post("/v1/schedules", json=payload)

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "agent_not_found"


# ---------------------------------------------------------------------------
# DELETE /v1/schedules/{id} — delete admin schedule
# ---------------------------------------------------------------------------


async def test_delete_admin_schedule_200(workspace: Path) -> None:
    """Happy path: delete an admin schedule returns 200."""
    gw = Gateway(workspace=str(workspace), auth=False)
    async with gw:
        gw._scheduler = _mock_scheduler()
        gw.get_schedule = AsyncMock(  # type: ignore[method-assign]
            return_value={"source": "admin", "schedule_id": "admin:test-agent:daily"}
        )
        gw.delete_admin_schedule = AsyncMock(return_value=True)  # type: ignore[method-assign]

        async with AsyncClient(
            transport=ASGITransport(app=gw),
            base_url="http://test",  # type: ignore[arg-type]
        ) as ac:
            resp = await ac.delete("/v1/schedules/admin:test-agent:daily")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "deleted"
    assert body["schedule_id"] == "admin:test-agent:daily"


async def test_delete_workspace_schedule_400(workspace: Path) -> None:
    """Attempting to delete a workspace schedule returns 400."""
    gw = Gateway(workspace=str(workspace), auth=False)
    async with gw:
        gw._scheduler = _mock_scheduler()
        gw.get_schedule = AsyncMock(  # type: ignore[method-assign]
            return_value={"source": "workspace", "schedule_id": "test-agent:daily"}
        )

        async with AsyncClient(
            transport=ASGITransport(app=gw),
            base_url="http://test",  # type: ignore[arg-type]
        ) as ac:
            resp = await ac.delete("/v1/schedules/test-agent:daily")

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "cannot_delete_workspace_schedule"
