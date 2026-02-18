"""Tests for workspace loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_gateway.workspace.loader import WorkspaceLoader, WorkspaceState

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
FIXTURE_WORKSPACE = FIXTURES_DIR / "workspace"


class TestWorkspaceLoader:
    @pytest.mark.asyncio
    async def test_load_fixture_workspace(self) -> None:
        state = await WorkspaceLoader.load(FIXTURE_WORKSPACE)
        assert len(state.errors) == 0
        assert "test-agent" in state.agents
        assert "test-skill" in state.skills
        assert "test-tool" in state.tools

    @pytest.mark.asyncio
    async def test_missing_workspace_dir(self, tmp_path: Path) -> None:
        state = await WorkspaceLoader.load(tmp_path / "nonexistent")
        assert len(state.errors) == 1
        assert "not found" in state.errors[0]

    @pytest.mark.asyncio
    async def test_workspace_not_a_directory(self, tmp_path: Path) -> None:
        file_path = tmp_path / "not-a-dir"
        file_path.write_text("hello")
        state = await WorkspaceLoader.load(file_path)
        assert len(state.errors) == 1
        assert "not a directory" in state.errors[0]

    @pytest.mark.asyncio
    async def test_empty_workspace(self, tmp_path: Path) -> None:
        state = await WorkspaceLoader.load(tmp_path)
        assert len(state.agents) == 0
        assert len(state.skills) == 0
        assert len(state.tools) == 0
        assert any("No agents/" in w for w in state.warnings)

    @pytest.mark.asyncio
    async def test_cross_reference_warnings(self, tmp_path: Path) -> None:
        """Agent referencing non-existent skill/tool produces warnings."""
        agents_dir = tmp_path / "agents"
        agent_dir = agents_dir / "my-agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENT.md").write_text("# Agent\n\nHello.")
        (agent_dir / "CONFIG.md").write_text(
            "---\nskills:\n  - nonexistent-skill\ntools:\n  - nonexistent-tool\n---\n"
        )

        state = await WorkspaceLoader.load(tmp_path)
        assert any("nonexistent-skill" in w for w in state.warnings)
        assert any("nonexistent-tool" in w for w in state.warnings)

    @pytest.mark.asyncio
    async def test_skill_cross_reference_warnings(self, tmp_path: Path) -> None:
        """Skill referencing non-existent tool produces warning."""
        skills_dir = tmp_path / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\ntools:\n  - ghost-tool\n---\n# Skill"
        )

        state = await WorkspaceLoader.load(tmp_path)
        assert any("ghost-tool" in w for w in state.warnings)

    @pytest.mark.asyncio
    async def test_root_system_prompt(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "AGENTS.md").write_text("# System Context\n\nYou are an AI.")

        state = await WorkspaceLoader.load(tmp_path)
        assert "You are an AI" in state.root_system_prompt

    @pytest.mark.asyncio
    async def test_root_soul_prompt(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "SOUL.md").write_text("# Soul\n\nBe kind.")

        state = await WorkspaceLoader.load(tmp_path)
        assert "Be kind" in state.root_soul_prompt

    @pytest.mark.asyncio
    async def test_schedules_collected(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents" / "cron-agent"
        agents_dir.mkdir(parents=True)
        (agents_dir / "AGENT.md").write_text("# Cron Agent\n\nRuns on schedule.")
        (agents_dir / "CONFIG.md").write_text(
            "---\nschedules:\n"
            "  - name: daily\n    cron: '0 9 * * *'\n    message: 'Do thing'\n"
            "---\n"
        )

        state = await WorkspaceLoader.load(tmp_path)
        assert len(state.schedules) == 1
        assert state.schedules[0].name == "daily"

    @pytest.mark.asyncio
    async def test_hidden_dirs_skipped(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents" / ".hidden-agent"
        agents_dir.mkdir(parents=True)
        (agents_dir / "AGENT.md").write_text("# Hidden\n\nShould be skipped.")

        state = await WorkspaceLoader.load(tmp_path)
        assert ".hidden-agent" not in state.agents


class TestWorkspaceState:
    def test_empty_factory(self) -> None:
        state = WorkspaceState.empty()
        assert state.path == Path(".")
        assert len(state.agents) == 0

    def test_empty_with_path(self, tmp_path: Path) -> None:
        state = WorkspaceState.empty(tmp_path)
        assert state.path == tmp_path
