"""Tests for the Slack notification backend."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

from agent_gateway.notifications.backends.slack import SlackBackend
from agent_gateway.notifications.models import NotificationEvent, NotificationTarget


def _make_event(**overrides: object) -> NotificationEvent:
    defaults = {
        "type": "execution.completed",
        "execution_id": "exec-789",
        "agent_id": "sales-agent",
        "status": "completed",
        "message": "Find leads for Q1 campaign",
        "duration_ms": 45000,
        "completed_at": datetime(2026, 2, 19, 14, 30, 0, tzinfo=UTC),
        "usage": {"total_tokens": 1200, "cost_usd": 0.0036},
    }
    defaults.update(overrides)
    return NotificationEvent(**defaults)  # type: ignore[arg-type]


class TestSlackBackendBlockKit:
    """Test the default Block Kit output."""

    def test_default_blocks_completed(self) -> None:
        backend = SlackBackend(bot_token="xoxb-test")
        event = _make_event()

        blocks = backend._default_blocks(event)

        # Header
        assert blocks[0]["type"] == "header"
        assert "Completed" in blocks[0]["text"]["text"]

        # Divider
        assert blocks[1]["type"] == "divider"

        # Fields section
        fields_section = blocks[2]
        assert fields_section["type"] == "section"
        field_texts = [f["text"] for f in fields_section["fields"]]
        assert any("sales-agent" in t for t in field_texts)
        assert any("exec-789" in t for t in field_texts)
        # Duration should be formatted
        assert any("45.0s" in t for t in field_texts)
        # Cost/usage should NOT be in blocks
        assert not any("$" in t for t in field_texts)

    def test_default_blocks_failed(self) -> None:
        backend = SlackBackend(bot_token="xoxb-test")
        event = _make_event(
            type="execution.failed",
            status="failed",
            error="LLM timeout after 60s",
            usage=None,
        )

        blocks = backend._default_blocks(event)

        assert "Failed" in blocks[0]["text"]["text"]
        # Error section should be present
        error_blocks = [
            b for b in blocks if b.get("text", {}).get("text", "").startswith("*Error*")
        ]
        assert len(error_blocks) == 1
        assert "LLM timeout" in error_blocks[0]["text"]["text"]

    def test_default_blocks_timeout(self) -> None:
        backend = SlackBackend(bot_token="xoxb-test")
        event = _make_event(type="execution.timeout", status="timeout")

        blocks = backend._default_blocks(event)
        assert "Timed Out" in blocks[0]["text"]["text"]

    def test_default_blocks_with_result(self) -> None:
        backend = SlackBackend(bot_token="xoxb-test")
        event = _make_event(result={"output": "Found 5 leads"})

        blocks = backend._default_blocks(event)
        result_blocks = [b for b in blocks if "Result" in b.get("text", {}).get("text", "")]
        assert len(result_blocks) == 1

    def test_message_truncation(self) -> None:
        backend = SlackBackend(bot_token="xoxb-test")
        event = _make_event(message="A" * 500)

        blocks = backend._default_blocks(event)
        input_blocks = [b for b in blocks if "*Input*" in b.get("text", {}).get("text", "")]
        assert len(input_blocks) == 1
        assert "..." in input_blocks[0]["text"]["text"]

    def test_duration_minutes_format(self) -> None:
        backend = SlackBackend(bot_token="xoxb-test")
        event = _make_event(duration_ms=120000)  # 2 minutes

        blocks = backend._default_blocks(event)
        fields = blocks[2]["fields"]
        duration_fields = [f for f in fields if "Duration" in f["text"]]
        assert len(duration_fields) == 1
        assert "2.0m" in duration_fields[0]["text"]

    def test_context_footer(self) -> None:
        backend = SlackBackend(bot_token="xoxb-test")
        event = _make_event()

        blocks = backend._default_blocks(event)
        context_block = blocks[-1]
        assert context_block["type"] == "context"
        assert "agent-gateway" in context_block["elements"][0]["text"]

    def test_fallback_text(self) -> None:
        backend = SlackBackend(bot_token="xoxb-test")
        event = _make_event()
        text = backend._build_fallback_text(event)
        assert "sales-agent" in text
        assert "exec-789" in text


class TestSlackBackendSend:
    async def test_send_posts_to_channel(self) -> None:
        backend = SlackBackend(bot_token="xoxb-test")
        await backend.initialize()

        event = _make_event()
        target = NotificationTarget(channel="slack", target="#agent-alerts")

        backend._client.chat_postMessage = AsyncMock()
        await backend.send(event, target)

        backend._client.chat_postMessage.assert_awaited_once()
        call_kwargs = backend._client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "#agent-alerts"
        assert isinstance(call_kwargs["blocks"], list)
        assert isinstance(call_kwargs["text"], str)

        await backend.dispose()

    async def test_send_uses_default_channel(self) -> None:
        backend = SlackBackend(bot_token="xoxb-test", default_channel="#my-default")
        await backend.initialize()

        event = _make_event()
        target = NotificationTarget(channel="slack")  # no target specified

        backend._client.chat_postMessage = AsyncMock()
        await backend.send(event, target)

        call_kwargs = backend._client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "#my-default"

        await backend.dispose()


class TestSlackBackendTemplates:
    def test_custom_template_rendering(self, tmp_path: Path) -> None:
        """Custom Jinja2 template is used when available."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        template_content = json.dumps(
            [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "Custom: {{ event.agent_id }}"},
                }
            ]
        )
        (templates_dir / "custom-alert.json.j2").write_text(template_content)

        backend = SlackBackend(bot_token="xoxb-test", templates_dir=templates_dir)
        event = _make_event()
        target = NotificationTarget(channel="slack", target="#alerts", template="custom-alert")

        blocks = backend._build_blocks(event, target)
        assert len(blocks) == 1
        assert "Custom: sales-agent" in blocks[0]["text"]["text"]

    def test_event_default_template(self, tmp_path: Path) -> None:
        """Event-type default template is used when no custom template specified."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        template_content = json.dumps(
            [{"type": "section", "text": {"type": "mrkdwn", "text": "Default completed"}}]
        )
        (templates_dir / "default-completed.json.j2").write_text(template_content)

        backend = SlackBackend(bot_token="xoxb-test", templates_dir=templates_dir)
        event = _make_event()
        target = NotificationTarget(channel="slack", target="#alerts")

        blocks = backend._build_blocks(event, target)
        assert blocks[0]["text"]["text"] == "Default completed"

    def test_falls_back_to_hardcoded_blocks(self, tmp_path: Path) -> None:
        """Falls back to hardcoded blocks when no templates exist."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        backend = SlackBackend(bot_token="xoxb-test", templates_dir=templates_dir)
        event = _make_event()
        target = NotificationTarget(channel="slack", target="#alerts")

        blocks = backend._build_blocks(event, target)
        assert blocks[0]["type"] == "header"
        assert "Completed" in blocks[0]["text"]["text"]

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        """Path traversal in template names falls back to default blocks."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        backend = SlackBackend(bot_token="xoxb-test", templates_dir=templates_dir)
        event = _make_event()
        target = NotificationTarget(
            channel="slack",
            target="#alerts",
            template="../../etc/passwd",
        )

        blocks = backend._build_blocks(event, target)
        assert blocks[0]["type"] == "header"
        assert "Completed" in blocks[0]["text"]["text"]
