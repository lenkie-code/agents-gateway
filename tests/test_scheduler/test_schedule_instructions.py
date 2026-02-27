"""Tests for schedule instructions feature — parsing, prompt assembly, engine flow, persistence."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_gateway.config import SchedulerConfig
from agent_gateway.persistence.backends.sql.repository import ScheduleRepository
from agent_gateway.persistence.backends.sqlite import SqliteBackend
from agent_gateway.persistence.domain import ScheduleRecord
from agent_gateway.persistence.null import NullScheduleRepository
from agent_gateway.queue.null import NullQueue
from agent_gateway.scheduler.engine import SchedulerEngine
from agent_gateway.workspace.agent import AgentDefinition, ScheduleConfig
from agent_gateway.workspace.loader import load_workspace
from agent_gateway.workspace.prompt import assemble_system_prompt

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_agent(tmp_path: Path, frontmatter: str, body: str = "# Agent\n\nDo stuff.\n") -> Path:
    agents = tmp_path / "agents"
    agents.mkdir(exist_ok=True)
    agent_dir = agents / "test-agent"
    agent_dir.mkdir(exist_ok=True)
    (agent_dir / "AGENT.md").write_text(f"---\n{frontmatter}---\n\n{body}")
    return agent_dir


def _make_engine(
    execution_repo: AsyncMock | None = None,
    invoke_fn: AsyncMock | None = None,
    schedule_repo: NullScheduleRepository | None = None,
) -> SchedulerEngine:
    return SchedulerEngine(
        config=SchedulerConfig(),
        schedule_repo=schedule_repo or NullScheduleRepository(),
        execution_repo=execution_repo or AsyncMock(),
        queue=NullQueue(),
        invoke_fn=invoke_fn or AsyncMock(),
        track_task=lambda t: None,
    )


# ---------------------------------------------------------------------------
# 1. _parse_schedules — instructions parsing
# ---------------------------------------------------------------------------


class TestParseScheduleInstructions:
    def test_instructions_present(self, tmp_path: Path) -> None:
        agent_dir = _write_agent(
            tmp_path,
            'schedules:\n  - name: daily\n    cron: "0 9 * * *"\n'
            '    message: "Run"\n    instructions: "Focus on errors"\n',
        )
        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.schedules[0].instructions == "Focus on errors"

    def test_instructions_absent(self, tmp_path: Path) -> None:
        agent_dir = _write_agent(
            tmp_path,
            'schedules:\n  - name: daily\n    cron: "0 9 * * *"\n    message: "Run"\n',
        )
        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.schedules[0].instructions is None

    def test_instructions_non_string_rejected(self, tmp_path: Path) -> None:
        agent_dir = _write_agent(
            tmp_path,
            'schedules:\n  - name: daily\n    cron: "0 9 * * *"\n'
            '    message: "Run"\n    instructions: 42\n',
        )
        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.schedules[0].instructions is None

    def test_instructions_truncated_at_4000_chars(self, tmp_path: Path) -> None:
        long_text = "x" * 5000
        agent_dir = _write_agent(
            tmp_path,
            f'schedules:\n  - name: daily\n    cron: "0 9 * * *"\n'
            f'    message: "Run"\n    instructions: "{long_text}"\n',
        )
        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.schedules[0].instructions is not None
        assert len(agent.schedules[0].instructions) == 4000


# ---------------------------------------------------------------------------
# 2. assemble_system_prompt — schedule_instructions block
# ---------------------------------------------------------------------------


class TestPromptScheduleInstructions:
    async def test_schedule_instructions_block_present(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agents" / "my-agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENT.md").write_text("# Agent\n\nHello.")

        state = load_workspace(tmp_path)
        agent = state.agents["my-agent"]
        prompt = await assemble_system_prompt(
            agent, state, schedule_instructions="Focus on errors"
        )
        assert "<schedule-instructions>" in prompt
        assert "Focus on errors" in prompt

    async def test_schedule_instructions_block_absent_when_none(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agents" / "my-agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENT.md").write_text("# Agent\n\nHello.")

        state = load_workspace(tmp_path)
        agent = state.agents["my-agent"]
        prompt = await assemble_system_prompt(agent, state, schedule_instructions=None)
        assert "<schedule-instructions>" not in prompt


# ---------------------------------------------------------------------------
# 3. SchedulerEngine — _schedule_instructions in job input_data
# ---------------------------------------------------------------------------


class TestEngineScheduleInstructions:
    async def test_register_job_includes_schedule_instructions(self) -> None:
        sched = ScheduleConfig(
            name="daily",
            cron="0 9 * * *",
            message="Run",
            instructions="Focus on errors",
        )
        agent = AgentDefinition(
            id="reporter",
            path=MagicMock(),
            agent_prompt="You are a reporter.",
            schedules=[sched],
        )

        engine = _make_engine()
        await engine.start(agents={"reporter": agent})

        job = engine._scheduler.get_job("reporter:daily")
        assert job is not None
        assert job.kwargs["input"]["_schedule_instructions"] == "Focus on errors"

        await engine.stop()

    async def test_register_job_omits_instructions_when_none(self) -> None:
        sched = ScheduleConfig(
            name="daily",
            cron="0 9 * * *",
            message="Run",
            instructions=None,
        )
        agent = AgentDefinition(
            id="reporter",
            path=MagicMock(),
            agent_prompt="You are a reporter.",
            schedules=[sched],
        )

        engine = _make_engine()
        await engine.start(agents={"reporter": agent})

        job = engine._scheduler.get_job("reporter:daily")
        assert "_schedule_instructions" not in job.kwargs["input"]

        await engine.stop()

    async def test_dispatch_strips_internal_keys_from_execution_record(self) -> None:
        """ExecutionRecord.input should NOT contain _-prefixed keys."""
        execution_repo = AsyncMock()
        sched = ScheduleConfig(
            name="daily",
            cron="0 9 * * *",
            message="Run",
            instructions="Focus on errors",
        )
        agent = AgentDefinition(
            id="reporter",
            path=MagicMock(),
            agent_prompt="You are a reporter.",
            schedules=[sched],
        )

        invoke_fn = AsyncMock()
        engine = _make_engine(execution_repo=execution_repo, invoke_fn=invoke_fn)
        await engine.start(agents={"reporter": agent})

        await engine.dispatch_scheduled_execution(
            schedule_id="reporter:daily",
            agent_id="reporter",
            message="Run",
            input={
                "source": "scheduled",
                "schedule_name": "daily",
                "_schedule_instructions": "Focus on errors",
                "_notify_config": {"channel": "slack"},
            },
        )

        # The persisted record should not have _-prefixed keys
        created_record = execution_repo.create.call_args[0][0]
        assert "_schedule_instructions" not in created_record.input
        assert "_notify_config" not in created_record.input
        assert created_record.input["source"] == "scheduled"

        # But invoke_fn should still receive the full input with internal keys
        invoke_fn.assert_called_once()
        invoke_input = invoke_fn.call_args[1]["input"]
        assert invoke_input["_schedule_instructions"] == "Focus on errors"

        await engine.stop()

    async def test_trigger_strips_internal_keys_from_execution_record(self) -> None:
        """trigger() should also strip _-prefixed keys from persisted record."""
        execution_repo = AsyncMock()
        invoke_fn = AsyncMock()
        invoke_fn.return_value = MagicMock(
            to_dict=lambda: {"raw_text": "done"},
            usage=MagicMock(to_dict=lambda: {"tokens": 10}),
        )
        sched = ScheduleConfig(
            name="daily",
            cron="0 9 * * *",
            message="Run",
            instructions="Focus on errors",
        )
        agent = AgentDefinition(
            id="reporter",
            path=MagicMock(),
            agent_prompt="You are a reporter.",
            schedules=[sched],
        )

        engine = _make_engine(execution_repo=execution_repo, invoke_fn=invoke_fn)
        await engine.start(agents={"reporter": agent})

        execution_id = await engine.trigger("reporter:daily")
        assert execution_id is not None

        await asyncio.sleep(0.2)

        created_record = execution_repo.create.call_args[0][0]
        assert "_schedule_instructions" not in created_record.input
        assert created_record.input["source"] == "manual_trigger"

        await engine.stop()


# ---------------------------------------------------------------------------
# 4. Persistence round-trip for instructions column
# ---------------------------------------------------------------------------


@pytest.fixture
async def sqlite_backend(tmp_path) -> SqliteBackend:
    db_path = tmp_path / "test_schedule_instructions.db"
    backend = SqliteBackend(path=str(db_path))
    await backend.initialize()
    yield backend
    await backend.dispose()


@pytest.fixture
def schedule_repo(sqlite_backend: SqliteBackend) -> ScheduleRepository:
    return ScheduleRepository(sqlite_backend._session_factory)


class TestPersistenceInstructionsRoundTrip:
    async def test_instructions_persisted_and_retrieved(
        self, schedule_repo: ScheduleRepository
    ) -> None:
        record = ScheduleRecord(
            id="agent:daily",
            agent_id="agent",
            name="daily",
            cron_expr="0 9 * * *",
            message="Run",
            instructions="Focus on errors",
            created_at=datetime.now(UTC),
        )
        await schedule_repo.upsert(record)

        result = await schedule_repo.get("agent:daily")
        assert result is not None
        assert result.instructions == "Focus on errors"

    async def test_instructions_null_when_absent(self, schedule_repo: ScheduleRepository) -> None:
        record = ScheduleRecord(
            id="agent:daily",
            agent_id="agent",
            name="daily",
            cron_expr="0 9 * * *",
            message="Run",
            created_at=datetime.now(UTC),
        )
        await schedule_repo.upsert(record)

        result = await schedule_repo.get("agent:daily")
        assert result is not None
        assert result.instructions is None


# ---------------------------------------------------------------------------
# 5. Regression: update_schedule(instructions=None) must NOT clear existing
# ---------------------------------------------------------------------------


class TestUpdateScheduleInstructionsRegression:
    async def test_update_schedule_instructions_none_preserves_existing(self) -> None:
        """Calling update_schedule with instructions=None should NOT clear existing value."""
        sched = ScheduleConfig(
            name="daily",
            cron="0 9 * * *",
            message="Run",
            instructions="Original instructions",
        )
        agent = AgentDefinition(
            id="reporter",
            path=MagicMock(),
            agent_prompt="You are a reporter.",
            schedules=[sched],
        )

        engine = _make_engine()
        await engine.start(agents={"reporter": agent})

        # Update only the message, not instructions
        result = await engine.update_schedule(
            "reporter:daily",
            message="Updated message",
            instructions=None,
        )
        assert result is True

        # In-memory config should still have original instructions
        config = engine._schedule_configs["reporter:daily"]
        assert config.instructions == "Original instructions"

        await engine.stop()

    async def test_update_schedule_instructions_explicit_empty_clears(self) -> None:
        """Passing instructions='' (empty string) should clear via the 'or None' logic."""
        sched = ScheduleConfig(
            name="daily",
            cron="0 9 * * *",
            message="Run",
            instructions="Original instructions",
        )
        agent = AgentDefinition(
            id="reporter",
            path=MagicMock(),
            agent_prompt="You are a reporter.",
            schedules=[sched],
        )

        engine = _make_engine()
        await engine.start(agents={"reporter": agent})

        result = await engine.update_schedule(
            "reporter:daily",
            instructions="",
        )
        assert result is True

        config = engine._schedule_configs["reporter:daily"]
        assert config.instructions is None

        await engine.stop()
