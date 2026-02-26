"""Tests for enabled field in AgentDefinition."""

from __future__ import annotations

from pathlib import Path

import yaml

from agent_gateway.workspace.agent import AgentDefinition


def _write_agent_md(agent_dir: Path, frontmatter: dict, body: str = "You are an agent.") -> None:
    agent_md = agent_dir / "AGENT.md"
    fm = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
    agent_md.write_text(f"---\n{fm}---\n\n{body}", encoding="utf-8")


class TestAgentEnabledField:
    def test_defaults_to_true_when_absent(self, tmp_path: Path) -> None:
        """Agent without enabled field in frontmatter defaults to enabled=True."""
        agent_dir = tmp_path / "test-agent"
        agent_dir.mkdir()
        _write_agent_md(agent_dir, {"description": "test"})
        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.enabled is True

    def test_reads_enabled_false_from_frontmatter(self, tmp_path: Path) -> None:
        """Agent with enabled: false in frontmatter has enabled=False."""
        agent_dir = tmp_path / "test-agent"
        agent_dir.mkdir()
        _write_agent_md(agent_dir, {"description": "test", "enabled": False})
        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.enabled is False

    def test_reads_enabled_true_from_frontmatter(self, tmp_path: Path) -> None:
        """Agent with enabled: true in frontmatter has enabled=True."""
        agent_dir = tmp_path / "test-agent"
        agent_dir.mkdir()
        _write_agent_md(agent_dir, {"description": "test", "enabled": True})
        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.enabled is True
