"""Tests for workspace loader."""

from __future__ import annotations

from pathlib import Path

from agent_gateway.workspace.loader import WorkspaceState, load_workspace

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
FIXTURE_WORKSPACE = FIXTURES_DIR / "workspace"


class TestLoadWorkspace:
    def test_load_fixture_workspace(self) -> None:
        state = load_workspace(FIXTURE_WORKSPACE)
        assert len(state.errors) == 0
        assert len(state.warnings) == 0
        assert "test-agent" in state.agents
        assert "test-skill" in state.skills
        assert "echo" in state.tools

    def test_missing_workspace_dir(self, tmp_path: Path) -> None:
        state = load_workspace(tmp_path / "nonexistent")
        assert len(state.errors) == 1
        assert "not found" in state.errors[0]

    def test_workspace_not_a_directory(self, tmp_path: Path) -> None:
        file_path = tmp_path / "not-a-dir"
        file_path.write_text("hello")
        state = load_workspace(file_path)
        assert len(state.errors) == 1
        assert "not a directory" in state.errors[0]

    def test_empty_workspace(self, tmp_path: Path) -> None:
        state = load_workspace(tmp_path)
        assert len(state.agents) == 0
        assert len(state.skills) == 0
        assert len(state.tools) == 0
        assert any("No agents/" in w for w in state.warnings)

    def test_cross_reference_warnings(self, tmp_path: Path) -> None:
        """Agent referencing non-existent skill produces warnings."""
        agents_dir = tmp_path / "agents"
        agent_dir = agents_dir / "my-agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENT.md").write_text(
            "---\nskills:\n  - nonexistent-skill\n---\n# Agent\n\nHello."
        )

        state = load_workspace(tmp_path)
        assert any("nonexistent-skill" in w for w in state.warnings)

    def test_skill_cross_reference_warnings(self, tmp_path: Path) -> None:
        """Skill referencing non-existent tool produces warning."""
        skills_dir = tmp_path / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\ntools:\n  - ghost-tool\n---\n# Skill"
        )

        state = load_workspace(tmp_path)
        assert any("ghost-tool" in w for w in state.warnings)

    def test_root_system_prompt(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "AGENTS.md").write_text("# System Context\n\nYou are an AI.")

        state = load_workspace(tmp_path)
        assert "You are an AI" in state.root_system_prompt

    def test_root_behavior_prompt(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "BEHAVIOR.md").write_text("# Behavior\n\nBe kind.")

        state = load_workspace(tmp_path)
        assert "Be kind" in state.root_behavior_prompt

    def test_schedules_collected(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents" / "cron-agent"
        agents_dir.mkdir(parents=True)
        (agents_dir / "AGENT.md").write_text(
            "---\nschedules:\n"
            "  - name: daily\n    cron: '0 9 * * *'\n    message: 'Do thing'\n"
            "---\n"
            "# Cron Agent\n\nRuns on schedule."
        )

        state = load_workspace(tmp_path)
        assert len(state.schedules) == 1
        assert state.schedules[0].name == "daily"

    def test_hidden_dirs_skipped(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents" / ".hidden-agent"
        agents_dir.mkdir(parents=True)
        (agents_dir / "AGENT.md").write_text("# Hidden\n\nShould be skipped.")

        state = load_workspace(tmp_path)
        assert ".hidden-agent" not in state.agents

    def test_symlinks_skipped(self, tmp_path: Path) -> None:
        """Symlinks inside workspace directories are skipped."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        real_dir = tmp_path / "outside" / "sneaky"
        real_dir.mkdir(parents=True)
        (real_dir / "AGENT.md").write_text("# Sneaky\n\nShould be skipped.")

        link = agents_dir / "sneaky"
        link.symlink_to(real_dir)

        state = load_workspace(tmp_path)
        assert "sneaky" not in state.agents

    def test_invalid_id_skipped(self, tmp_path: Path) -> None:
        """Directories with invalid IDs produce warnings."""
        agents_dir = tmp_path / "agents" / "INVALID ID"
        agents_dir.mkdir(parents=True)
        (agents_dir / "AGENT.md").write_text("# Agent\n\nHello.")

        state = load_workspace(tmp_path)
        assert "INVALID ID" not in state.agents
        assert any("invalid ID" in w for w in state.warnings)


class TestWorkspaceState:
    def test_constructor(self, tmp_path: Path) -> None:
        state = WorkspaceState(path=tmp_path)
        assert state.path == tmp_path
        assert len(state.agents) == 0
