"""Integration tests for delegate_to_agent built-in tool."""

from __future__ import annotations

from pathlib import Path

from agent_gateway.gateway import Gateway


def _make_workspace(tmp_path: Path, agents: dict[str, str]) -> Path:
    """Create a minimal workspace with the given agents.

    Args:
        agents: mapping of agent_id -> AGENT.md content
    """
    ws = tmp_path / "workspace"
    agents_dir = ws / "agents"
    agents_dir.mkdir(parents=True)
    for aid, content in agents.items():
        d = agents_dir / aid
        d.mkdir()
        (d / "AGENT.md").write_text(content)
    return ws


class TestDelegationToolRegistration:
    """Integration tests for delegation tool registration."""

    async def test_delegation_available_in_multi_agent_workspace(self, tmp_path: Path) -> None:
        """delegate_to_agent is registered when workspace has 2+ agents."""
        ws = _make_workspace(
            tmp_path,
            {
                "agent-a": "---\ndescription: A\n---\nAgent A",
                "agent-b": "---\ndescription: B\n---\nAgent B",
            },
        )
        async with Gateway(workspace=str(ws), auth=False) as gw:
            registry = gw._snapshot.tool_registry
            all_tools = registry.get_all()
            assert "delegate_to_agent" in all_tools
            tool = all_tools["delegate_to_agent"]
            # available to all agents (allowed_agents is None)
            assert tool.allows_agent("agent-a")
            assert tool.allows_agent("agent-b")

    async def test_delegation_not_registered_single_agent(self, tmp_path: Path) -> None:
        """delegate_to_agent is NOT registered with only 1 agent."""
        ws = _make_workspace(
            tmp_path,
            {"solo": "---\ndescription: Solo\n---\nSolo agent"},
        )
        async with Gateway(workspace=str(ws), auth=False) as gw:
            all_tools = gw._snapshot.tool_registry.get_all()
            assert "delegate_to_agent" not in all_tools

    async def test_delegation_description_lists_agents(self, tmp_path: Path) -> None:
        """Tool description includes available agent IDs."""
        ws = _make_workspace(
            tmp_path,
            {
                "alpha": "---\ndescription: Alpha\n---\nAlpha",
                "beta": "---\ndescription: Beta\n---\nBeta",
            },
        )
        async with Gateway(workspace=str(ws), auth=False) as gw:
            tool = gw._snapshot.tool_registry.get_all()["delegate_to_agent"]
            assert "alpha" in tool.description
            assert "beta" in tool.description

    async def test_delegation_tool_survives_reload(self, tmp_path: Path) -> None:
        """delegate_to_agent persists after workspace reload."""
        ws = _make_workspace(
            tmp_path,
            {
                "agent-a": "---\ndescription: A\n---\nAgent A",
                "agent-b": "---\ndescription: B\n---\nAgent B",
            },
        )
        async with Gateway(workspace=str(ws), auth=False) as gw:
            assert "delegate_to_agent" in gw._snapshot.tool_registry.get_all()
            await gw.reload()
            assert "delegate_to_agent" in gw._snapshot.tool_registry.get_all()

    async def test_reload_removes_delegation_when_agents_drop_to_one(self, tmp_path: Path) -> None:
        """Reload with only 1 agent removes the delegation tool."""
        ws = _make_workspace(
            tmp_path,
            {
                "agent-a": "---\ndescription: A\n---\nAgent A",
                "agent-b": "---\ndescription: B\n---\nAgent B",
            },
        )
        async with Gateway(workspace=str(ws), auth=False) as gw:
            assert "delegate_to_agent" in gw._snapshot.tool_registry.get_all()
            # Remove agent-b from disk
            import shutil

            shutil.rmtree(ws / "agents" / "agent-b")
            await gw.reload()
            assert "delegate_to_agent" not in gw._snapshot.tool_registry.get_all()

    async def test_reload_adds_delegation_when_agents_grow_to_two(self, tmp_path: Path) -> None:
        """Reload with 2 agents adds delegation tool that wasn't there before."""
        ws = _make_workspace(
            tmp_path,
            {"solo": "---\ndescription: Solo\n---\nSolo agent"},
        )
        async with Gateway(workspace=str(ws), auth=False) as gw:
            assert "delegate_to_agent" not in gw._snapshot.tool_registry.get_all()
            # Add a second agent
            new_agent = ws / "agents" / "partner"
            new_agent.mkdir()
            (new_agent / "AGENT.md").write_text("---\ndescription: Partner\n---\nPartner agent")
            await gw.reload()
            assert "delegate_to_agent" in gw._snapshot.tool_registry.get_all()
