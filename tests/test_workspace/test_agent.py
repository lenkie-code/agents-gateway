"""Tests for agent model loading."""

from __future__ import annotations

from pathlib import Path

from agent_gateway.workspace.agent import AgentDefinition


class TestAgentDefinition:
    def test_load_minimal_agent(self, tmp_path: Path) -> None:
        """Agent with only AGENT.md."""
        agent_dir = tmp_path / "my-agent"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text("# My Agent\n\nYou are helpful.")

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.id == "my-agent"
        assert "You are helpful" in agent.agent_prompt
        assert agent.behavior_prompt == ""
        assert agent.skills == []
        assert agent.tools == []
        assert agent.schedules == []

    def test_load_full_agent(self, tmp_path: Path) -> None:
        """Agent with AGENT.md + BEHAVIOR.md."""
        agent_dir = tmp_path / "full-agent"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\n"
            "skills:\n  - math-workflow\n"
            "tools:\n  - echo\n  - add-numbers\n"
            "model:\n  name: gpt-4o\n  temperature: 0.5\n"
            "---\n"
            "# Full Agent\n\nDoes everything."
        )
        (agent_dir / "BEHAVIOR.md").write_text("# Behavior\n\nFriendly and helpful.")

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.id == "full-agent"
        assert "Does everything" in agent.agent_prompt
        assert "Friendly and helpful" in agent.behavior_prompt
        assert agent.skills == ["math-workflow"]
        assert agent.tools == ["echo", "add-numbers"]
        assert agent.model.name == "gpt-4o"
        assert agent.model.temperature == 0.5

    def test_missing_agent_md_returns_none(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "no-agent"
        agent_dir.mkdir()
        assert AgentDefinition.load(agent_dir) is None

    def test_empty_agent_md_returns_none(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "empty-agent"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text("")
        assert AgentDefinition.load(agent_dir) is None

    def test_agent_with_schedules(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "scheduled"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\n"
            "schedules:\n"
            "  - name: daily-report\n"
            "    cron: '0 9 * * 1-5'\n"
            "    message: 'Generate daily report'\n"
            "    enabled: true\n"
            "    timezone: Europe/London\n"
            "  - name: weekly-scan\n"
            "    cron: '0 6 * * 1'\n"
            "    message: 'Run weekly scan'\n"
            "    enabled: false\n"
            "---\n"
            "# Scheduled Agent\n\nRuns on cron."
        )

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert len(agent.schedules) == 2
        assert agent.schedules[0].name == "daily-report"
        assert agent.schedules[0].cron == "0 9 * * 1-5"
        assert agent.schedules[0].timezone == "Europe/London"
        assert agent.schedules[0].enabled is True
        assert agent.schedules[1].name == "weekly-scan"
        assert agent.schedules[1].enabled is False

    def test_agent_with_invalid_schedule(self, tmp_path: Path) -> None:
        """Invalid schedule entries are skipped with warning."""
        agent_dir = tmp_path / "bad-schedule"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\nschedules:\n  - name: missing-fields\n---\n# Agent\n\nHello."
        )

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert len(agent.schedules) == 0

    def test_agent_with_model_config(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "model-agent"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\n"
            "model:\n"
            "  name: claude-3-opus\n"
            "  temperature: 0.0\n"
            "  max_tokens: 8192\n"
            "  fallback: gpt-4o\n"
            "---\n"
            "# Agent\n\nHello."
        )

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.model.name == "claude-3-opus"
        assert agent.model.temperature == 0.0
        assert agent.model.max_tokens == 8192
        assert agent.model.fallback == "gpt-4o"

    def test_frontmatter_tools_in_agent_md(self, tmp_path: Path) -> None:
        """Tools defined in AGENT.md frontmatter are loaded."""
        agent_dir = tmp_path / "fm-agent"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\n"
            "tools:\n  - weather\n  - flights\n"
            "skills:\n  - planner\n"
            "---\n"
            "# Agent\n\nPlans trips."
        )

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.tools == ["weather", "flights"]
        assert agent.skills == ["planner"]

    def test_frontmatter_schedules_in_agent_md(self, tmp_path: Path) -> None:
        """Schedules defined in AGENT.md frontmatter are loaded."""
        agent_dir = tmp_path / "sched-fm"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\n"
            "schedules:\n"
            "  - name: nightly\n"
            "    cron: '0 0 * * *'\n"
            "    message: 'Run nightly'\n"
            "---\n"
            "# Agent\n\nScheduled via frontmatter."
        )

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert len(agent.schedules) == 1
        assert agent.schedules[0].name == "nightly"
        assert agent.schedules[0].cron == "0 0 * * *"
