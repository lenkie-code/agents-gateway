"""Tests for agent notification parsing from AGENT.md frontmatter."""

from __future__ import annotations

from pathlib import Path

from agent_gateway.workspace.agent import AgentDefinition


class TestAgentNotificationParsing:
    def test_agent_with_slack_notifications(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\n"
            "notifications:\n"
            "  on_complete:\n"
            "    - channel: slack\n"
            "      target: '#agent-alerts'\n"
            "---\n"
            "# Agent\n\nHello."
        )

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert len(agent.notifications.on_complete) == 1
        assert agent.notifications.on_complete[0].channel == "slack"
        assert agent.notifications.on_complete[0].target == "#agent-alerts"

    def test_agent_with_webhook_inline(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\n"
            "notifications:\n"
            "  on_complete:\n"
            "    - channel: webhook\n"
            "      url: https://crm.example.com/hook\n"
            "  on_error:\n"
            "    - channel: webhook\n"
            "      url: https://pagerduty.example.com/alert\n"
            "---\n"
            "# Agent\n\nHello."
        )

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert len(agent.notifications.on_complete) == 1
        assert agent.notifications.on_complete[0].url == "https://crm.example.com/hook"
        assert len(agent.notifications.on_error) == 1
        assert agent.notifications.on_error[0].url == "https://pagerduty.example.com/alert"

    def test_agent_with_webhook_global_reference(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\n"
            "notifications:\n"
            "  on_complete:\n"
            "    - channel: webhook\n"
            "      target: crm-integration\n"
            "---\n"
            "# Agent\n\nHello."
        )

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.notifications.on_complete[0].target == "crm-integration"

    def test_agent_with_multiple_targets(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\n"
            "notifications:\n"
            "  on_complete:\n"
            "    - channel: slack\n"
            "      target: '#sales-alerts'\n"
            "    - channel: webhook\n"
            "      url: https://crm.example.com/hook\n"
            "  on_error:\n"
            "    - channel: slack\n"
            "      target: '#engineering-oncall'\n"
            "  on_timeout:\n"
            "    - channel: webhook\n"
            "      url: https://pagerduty.example.com/alert\n"
            "---\n"
            "# Agent\n\nHello."
        )

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert len(agent.notifications.on_complete) == 2
        assert len(agent.notifications.on_error) == 1
        assert len(agent.notifications.on_timeout) == 1

    def test_agent_without_notifications(self, tmp_path: Path) -> None:
        """Agent with no notification config gets empty AgentNotificationConfig."""
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text("---\nmodel:\n  name: gpt-4o\n---\n# Agent\n\nHello.")

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert len(agent.notifications.on_complete) == 0
        assert len(agent.notifications.on_error) == 0
        assert len(agent.notifications.on_timeout) == 0

    def test_agent_with_custom_template(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\n"
            "notifications:\n"
            "  on_complete:\n"
            "    - channel: slack\n"
            "      target: '#alerts'\n"
            "      template: sales-completed\n"
            "---\n"
            "# Agent\n\nHello."
        )

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.notifications.on_complete[0].template == "sales-completed"

    def test_agent_with_payload_template(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\n"
            "notifications:\n"
            "  on_complete:\n"
            "    - channel: webhook\n"
            "      url: https://example.com/hook\n"
            '      payload_template: \'{"agent": "{{ event.agent_id }}"}\'\n'
            "---\n"
            "# Agent\n\nHello."
        )

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert agent.notifications.on_complete[0].payload_template is not None
        assert "event.agent_id" in agent.notifications.on_complete[0].payload_template

    def test_notifications_in_agent_md_frontmatter(self, tmp_path: Path) -> None:
        """Notifications defined in AGENT.md frontmatter."""
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\n"
            "notifications:\n"
            "  on_complete:\n"
            "    - channel: slack\n"
            "      target: '#alerts'\n"
            "---\n"
            "# Agent\n\nHello."
        )

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        assert len(agent.notifications.on_complete) == 1
        assert agent.notifications.on_complete[0].channel == "slack"

    def test_invalid_notification_config_ignored(self, tmp_path: Path) -> None:
        """Malformed notification config doesn't crash agent loading."""
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "AGENT.md").write_text(
            "---\nnotifications:\n  on_complete: not-a-list\n---\n# Agent\n\nHello."
        )

        agent = AgentDefinition.load(agent_dir)
        assert agent is not None
        # Should have empty notifications (graceful degradation)
        assert len(agent.notifications.on_complete) == 0
