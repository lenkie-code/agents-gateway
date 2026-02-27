"""Tests for admin-created dynamic schedules in SchedulerEngine."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_gateway.config import SchedulerConfig
from agent_gateway.exceptions import ScheduleConflictError, ScheduleValidationError
from agent_gateway.persistence.null import NullScheduleRepository
from agent_gateway.queue.null import NullQueue
from agent_gateway.scheduler.engine import SchedulerEngine
from agent_gateway.workspace.agent import AgentDefinition, ScheduleConfig


def _make_agent(
    agent_id: str = "reporter",
    schedules: list[ScheduleConfig] | None = None,
) -> AgentDefinition:
    return AgentDefinition(
        id=agent_id,
        path=MagicMock(),
        agent_prompt="You are a reporter.",
        schedules=schedules or [],
    )


def _make_schedule(
    name: str = "daily-report",
    cron: str = "0 9 * * *",
    message: str = "Generate report",
    enabled: bool = True,
) -> ScheduleConfig:
    return ScheduleConfig(name=name, cron=cron, message=message, enabled=enabled)


def _make_engine(
    schedule_repo: NullScheduleRepository | None = None,
) -> SchedulerEngine:
    return SchedulerEngine(
        config=SchedulerConfig(),
        schedule_repo=schedule_repo or NullScheduleRepository(),
        execution_repo=AsyncMock(),
        queue=NullQueue(),
        invoke_fn=AsyncMock(),
        track_task=lambda t: None,
    )


class TestCreateAdminSchedule:
    async def test_creates_and_registers_job(self) -> None:
        """Admin schedule should be persisted, registered in memory and APScheduler."""
        sched = _make_schedule()
        agent = _make_agent(schedules=[sched])
        repo = NullScheduleRepository()
        engine = _make_engine(schedule_repo=repo)

        await engine.start({"reporter": agent})

        schedule_id = await engine.create_admin_schedule(
            agent_id="reporter",
            name="weekly-digest",
            cron_expr="0 10 * * 1",
            message="Weekly digest",
        )

        assert schedule_id == "admin:reporter:weekly-digest"
        assert schedule_id in engine._schedule_configs
        assert engine._agent_map[schedule_id] == "reporter"

        # Check persistence
        rec = await repo.get(schedule_id)
        assert rec is not None
        assert rec.source == "admin"
        assert rec.message == "Weekly digest"

        # Check APScheduler job
        assert engine._scheduler is not None
        job = engine._scheduler.get_job(schedule_id)
        assert job is not None

        await engine.stop()

    async def test_invalid_cron_raises_validation_error(self) -> None:
        """Bad cron expression should raise ScheduleValidationError."""
        agent = _make_agent(schedules=[_make_schedule()])
        engine = _make_engine()
        await engine.start({"reporter": agent})

        with pytest.raises(ScheduleValidationError):
            await engine.create_admin_schedule(
                agent_id="reporter",
                name="bad-cron",
                cron_expr="not a cron",
                message="test",
            )

        await engine.stop()

    async def test_duplicate_name_raises_conflict_error(self) -> None:
        """Creating duplicate schedule should raise ScheduleConflictError."""
        agent = _make_agent(schedules=[_make_schedule()])
        engine = _make_engine()
        await engine.start({"reporter": agent})

        await engine.create_admin_schedule(
            agent_id="reporter",
            name="weekly",
            cron_expr="0 10 * * 1",
            message="test",
        )

        with pytest.raises(ScheduleConflictError):
            await engine.create_admin_schedule(
                agent_id="reporter",
                name="weekly",
                cron_expr="0 10 * * 1",
                message="test again",
            )

        await engine.stop()

    async def test_unknown_agent_raises_validation_error(self) -> None:
        """Unknown agent_id should raise ScheduleValidationError."""
        agent = _make_agent(schedules=[_make_schedule()])
        engine = _make_engine()
        await engine.start({"reporter": agent})

        with pytest.raises(ScheduleValidationError, match="Unknown agent"):
            await engine.create_admin_schedule(
                agent_id="nonexistent",
                name="test",
                cron_expr="0 10 * * 1",
                message="test",
            )

        await engine.stop()


class TestDeleteAdminSchedule:
    async def test_deletes_admin_schedule(self) -> None:
        """Admin schedule should be removed from APScheduler and soft-deleted."""
        agent = _make_agent(schedules=[_make_schedule()])
        repo = NullScheduleRepository()
        engine = _make_engine(schedule_repo=repo)
        await engine.start({"reporter": agent})

        sid = await engine.create_admin_schedule(
            agent_id="reporter",
            name="to-delete",
            cron_expr="0 10 * * 1",
            message="test",
        )

        ok = await engine.delete_admin_schedule(sid)
        assert ok is True

        # Memory cleaned up
        assert sid not in engine._schedule_configs
        assert sid not in engine._agent_map

        # Soft-deleted in persistence
        rec = await repo.get(sid)
        assert rec is not None
        assert rec.deleted_at is not None

        await engine.stop()

    async def test_rejects_workspace_schedule(self) -> None:
        """Workspace schedules should not be deletable."""
        sched = _make_schedule(name="workspace-sched")
        agent = _make_agent(schedules=[sched])
        engine = _make_engine()
        await engine.start({"reporter": agent})

        ok = await engine.delete_admin_schedule("reporter:workspace-sched")
        assert ok is False

        await engine.stop()

    async def test_returns_false_for_missing(self) -> None:
        """Should return False for nonexistent schedule."""
        agent = _make_agent(schedules=[_make_schedule()])
        engine = _make_engine()
        await engine.start({"reporter": agent})

        ok = await engine.delete_admin_schedule("admin:reporter:no-such")
        assert ok is False

        await engine.stop()


class TestLoadAdminSchedules:
    async def test_admin_schedules_loaded_on_startup(self) -> None:
        """Admin schedules in DB should be loaded into memory on start()."""
        repo = NullScheduleRepository()

        # Pre-seed an admin schedule in the repo
        from agent_gateway.persistence.domain import ScheduleRecord

        rec = ScheduleRecord(
            id="admin:reporter:preseeded",
            agent_id="reporter",
            name="preseeded",
            cron_expr="0 8 * * *",
            message="Pre-seeded admin schedule",
            source="admin",
        )
        await repo.upsert(rec)

        sched = _make_schedule()
        agent = _make_agent(schedules=[sched])
        engine = _make_engine(schedule_repo=repo)
        await engine.start({"reporter": agent})

        assert "admin:reporter:preseeded" in engine._schedule_configs
        assert engine._agent_map["admin:reporter:preseeded"] == "reporter"

        # Should also have a job in APScheduler
        assert engine._scheduler is not None
        job = engine._scheduler.get_job("admin:reporter:preseeded")
        assert job is not None

        await engine.stop()


class TestSyncDoesNotOverwriteAdmin:
    async def test_workspace_sync_skips_admin_records(self) -> None:
        """upsert_batch during workspace sync should not overwrite admin schedules."""
        repo = NullScheduleRepository()

        # Pre-seed an admin schedule
        from agent_gateway.persistence.domain import ScheduleRecord

        rec = ScheduleRecord(
            id="admin:reporter:custom",
            agent_id="reporter",
            name="custom",
            cron_expr="0 12 * * *",
            message="Custom admin message",
            source="admin",
        )
        await repo.upsert(rec)

        sched = _make_schedule()
        agent = _make_agent(schedules=[sched])
        engine = _make_engine(schedule_repo=repo)
        await engine.start({"reporter": agent})

        # Admin schedule should still have its original message
        stored = await repo.get("admin:reporter:custom")
        assert stored is not None
        assert stored.message == "Custom admin message"
        assert stored.source == "admin"

        await engine.stop()


class TestSourceInResponses:
    async def test_get_schedules_includes_source(self) -> None:
        """get_schedules should include source field."""
        sched = _make_schedule()
        agent = _make_agent(schedules=[sched])
        engine = _make_engine()
        await engine.start({"reporter": agent})

        schedules = await engine.get_schedules()
        assert len(schedules) >= 1
        assert schedules[0]["source"] == "workspace"

        await engine.stop()

    async def test_get_schedule_includes_source(self) -> None:
        """get_schedule should include source field."""
        sched = _make_schedule()
        agent = _make_agent(schedules=[sched])
        engine = _make_engine()
        await engine.start({"reporter": agent})

        detail = await engine.get_schedule("reporter:daily-report")
        assert detail is not None
        assert detail["source"] == "workspace"

        await engine.stop()
