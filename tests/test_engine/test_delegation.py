"""Tests for agent-to-agent delegation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from agent_gateway.config import GatewayConfig, GuardrailsConfig
from agent_gateway.engine.delegation import run_delegation
from agent_gateway.engine.models import ExecutionResult, StopReason
from agent_gateway.persistence.domain import ExecutionRecord
from agent_gateway.workspace.agent import AgentDefinition


def _make_mock_gateway(
    agents: dict[str, MagicMock] | None = None,
) -> MagicMock:
    """Create a mock gateway with agents property."""
    gw = MagicMock()
    gw._config = GatewayConfig()
    gw._config.guardrails = GuardrailsConfig(max_delegation_depth=3)
    if agents is None:
        # Default: writer and researcher, both enabled
        writer = MagicMock()
        writer.enabled = True
        researcher = MagicMock()
        researcher.enabled = True
        agents = {"writer": writer, "researcher": researcher}
    type(gw).agents = PropertyMock(return_value=agents)
    gw.is_agent_enabled = lambda aid: agents.get(aid) is not None and agents[aid].enabled
    return gw


class TestRunDelegation:
    """Tests for the run_delegation function."""

    @pytest.fixture
    def mock_gateway(self) -> MagicMock:
        return _make_mock_gateway()

    @pytest.mark.asyncio
    async def test_permission_denied(self, mock_gateway: MagicMock) -> None:
        """Returns error when agent_id not in delegates_to."""
        result = await run_delegation(
            mock_gateway,
            caller_agent_id="coordinator",
            delegates_to=["writer"],
            execution_id="exec-1",
            root_execution_id="root-1",
            delegation_depth=0,
            user_id=None,
            agent_id="hacker",
            message="do something",
        )
        assert "Error" in result
        assert "does not exist" in result
        assert "hacker" in result

    @pytest.mark.asyncio
    async def test_restricted_delegates_to_blocks_unlisted(self, mock_gateway: MagicMock) -> None:
        """Returns error when agent exists but is not in delegates_to allow-list."""
        result = await run_delegation(
            mock_gateway,
            caller_agent_id="coordinator",
            delegates_to=["writer"],
            execution_id="exec-1",
            root_execution_id="root-1",
            delegation_depth=0,
            user_id=None,
            agent_id="researcher",
            message="do something",
        )
        assert "Error" in result
        assert "not allowed" in result
        assert "researcher" in result

    @pytest.mark.asyncio
    async def test_max_depth_reached(self, mock_gateway: MagicMock) -> None:
        """Returns error when max delegation depth is reached."""
        result = await run_delegation(
            mock_gateway,
            caller_agent_id="coordinator",
            delegates_to=["writer"],
            execution_id="exec-1",
            root_execution_id="root-1",
            delegation_depth=3,  # at max
            user_id=None,
            agent_id="writer",
            message="do something",
        )
        assert "Error" in result
        assert "Maximum delegation depth" in result

    @pytest.mark.asyncio
    async def test_successful_delegation(self, mock_gateway: MagicMock) -> None:
        """Successfully delegates and returns result text."""
        mock_result = ExecutionResult(
            raw_text="I completed the task.",
            stop_reason=StopReason.COMPLETED,
        )
        mock_gateway.invoke = AsyncMock(return_value=mock_result)

        result = await run_delegation(
            mock_gateway,
            caller_agent_id="coordinator",
            delegates_to=["writer"],
            execution_id="exec-1",
            root_execution_id="root-1",
            delegation_depth=0,
            user_id=None,
            agent_id="writer",
            message="write a report",
        )
        assert result == "I completed the task."
        mock_gateway.invoke.assert_awaited_once_with(
            agent_id="writer",
            message="write a report",
            input=None,
            parent_execution_id="exec-1",
            root_execution_id="root-1",
            delegation_depth=1,
        )

    @pytest.mark.asyncio
    async def test_delegation_exception_handling(self, mock_gateway: MagicMock) -> None:
        """Returns error string when delegation raises."""
        mock_gateway.invoke = AsyncMock(side_effect=ValueError("Agent not found"))

        result = await run_delegation(
            mock_gateway,
            caller_agent_id="coordinator",
            delegates_to=["writer"],
            execution_id="exec-1",
            root_execution_id="root-1",
            delegation_depth=0,
            user_id=None,
            agent_id="writer",
            message="write a report",
        )
        assert "Error" in result
        assert "failed" in result

    @pytest.mark.asyncio
    async def test_self_delegation_blocked(self, mock_gateway: MagicMock) -> None:
        """Agent cannot delegate to itself."""
        result = await run_delegation(
            mock_gateway,
            caller_agent_id="writer",
            delegates_to=["writer"],
            execution_id="exec-1",
            root_execution_id="root-1",
            delegation_depth=0,
            user_id=None,
            agent_id="writer",
            message="do something",
        )
        assert "Error" in result
        assert "cannot delegate to itself" in result

    @pytest.mark.asyncio
    async def test_unrestricted_when_no_delegates_to(self, mock_gateway: MagicMock) -> None:
        """Agent without delegates_to can delegate to any enabled agent."""
        mock_result = ExecutionResult(
            raw_text="Done.",
            stop_reason=StopReason.COMPLETED,
        )
        mock_gateway.invoke = AsyncMock(return_value=mock_result)

        result = await run_delegation(
            mock_gateway,
            caller_agent_id="coordinator",
            delegates_to=[],  # unrestricted
            execution_id="exec-1",
            root_execution_id="root-1",
            delegation_depth=0,
            user_id=None,
            agent_id="writer",
            message="write a report",
        )
        assert result == "Done."
        mock_gateway.invoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delegation_to_disabled_agent_blocked(self) -> None:
        """Delegating to a disabled agent returns error."""
        writer = MagicMock()
        writer.enabled = False
        gw = _make_mock_gateway(agents={"writer": writer})

        result = await run_delegation(
            gw,
            caller_agent_id="coordinator",
            delegates_to=[],
            execution_id="exec-1",
            root_execution_id="root-1",
            delegation_depth=0,
            user_id=None,
            agent_id="writer",
            message="write a report",
        )
        assert "Error" in result
        assert "disabled" in result

    @pytest.mark.asyncio
    async def test_delegation_to_nonexistent_agent_returns_error(
        self, mock_gateway: MagicMock
    ) -> None:
        """Delegating to a non-existent agent returns error listing available agents."""
        result = await run_delegation(
            mock_gateway,
            caller_agent_id="coordinator",
            delegates_to=[],
            execution_id="exec-1",
            root_execution_id="root-1",
            delegation_depth=0,
            user_id=None,
            agent_id="ghost",
            message="do something",
        )
        assert "Error" in result
        assert "does not exist" in result
        assert "Available agents" in result


class TestAgentDefinitionDelegatesTo:
    """Tests for delegates_to parsing from frontmatter."""

    def test_delegates_to_parsed(self, tmp_path: Path) -> None:
        """delegates_to list is parsed from AGENT.md frontmatter."""
        agent_dir = tmp_path / "coordinator"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\n"
            "description: Coordinator\n"
            "delegates_to:\n"
            "  - writer\n"
            "  - researcher\n"
            "---\n"
            "You are a coordinator agent.\n"
        )
        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.delegates_to == ["writer", "researcher"]

    def test_delegates_to_empty_by_default(self, tmp_path: Path) -> None:
        """delegates_to defaults to empty list."""
        agent_dir = tmp_path / "basic"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\ndescription: Basic agent\n---\nYou are a basic agent.\n"
        )
        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.delegates_to == []

    def test_delegates_to_invalid_ignored(self, tmp_path: Path) -> None:
        """Invalid delegates_to value is ignored."""
        agent_dir = tmp_path / "bad"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\ndescription: Bad agent\ndelegates_to: not-a-list\n---\nYou are a bad agent.\n"
        )
        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.delegates_to == []


class TestExecutionRecordDelegationFields:
    """Tests for delegation fields on ExecutionRecord."""

    def test_default_values(self) -> None:
        record = ExecutionRecord(id="1", agent_id="test")
        assert record.parent_execution_id is None
        assert record.root_execution_id is None
        assert record.delegation_depth == 0

    def test_set_values(self) -> None:
        record = ExecutionRecord(
            id="child-1",
            agent_id="writer",
            parent_execution_id="parent-1",
            root_execution_id="root-1",
            delegation_depth=2,
        )
        assert record.parent_execution_id == "parent-1"
        assert record.root_execution_id == "root-1"
        assert record.delegation_depth == 2
