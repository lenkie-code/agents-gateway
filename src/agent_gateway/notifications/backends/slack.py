"""Slack notification backend using Block Kit rich formatting.

Requires: pip install agent-gateway[slack]
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_gateway.notifications.models import NotificationEvent, NotificationTarget

logger = logging.getLogger(__name__)

# Status config: emoji, display text, color (for attachment fallback)
_STATUS_CONFIG: dict[str, tuple[str, str, str]] = {
    "execution.completed": (":white_check_mark:", "Completed", "#36a64f"),
    "execution.failed": (":x:", "Failed", "#e01e5a"),
    "execution.timeout": (":warning:", "Timed Out", "#ecb22e"),
}


class SlackBackend:
    """Slack notification backend using Block Kit rich formatting.

    Requires: pip install agent-gateway[slack]
    """

    def __init__(
        self,
        bot_token: str,
        default_channel: str = "#agent-alerts",
        templates_dir: Path | None = None,
    ) -> None:
        try:
            from slack_sdk.web.async_client import AsyncWebClient  # noqa: F401
        except ImportError:
            raise ImportError(
                "Slack backend requires the slack extra: "
                "pip install agent-gateway[slack]"
            ) from None

        self._bot_token = bot_token
        self._default_channel = default_channel
        self._templates_dir = templates_dir
        self._client: Any = None  # AsyncWebClient, typed as Any to avoid import at module level

    @property
    def channel(self) -> str:
        return "slack"

    async def initialize(self) -> None:
        from slack_sdk.web.async_client import AsyncWebClient

        self._client = AsyncWebClient(token=self._bot_token)

    async def dispose(self) -> None:
        self._client = None

    async def send(
        self,
        event: NotificationEvent,
        target: NotificationTarget,
    ) -> None:
        if self._client is None:
            raise RuntimeError("SlackBackend not initialized — call initialize() first")

        channel = target.target or self._default_channel
        blocks = self._build_blocks(event, target)
        fallback_text = self._build_fallback_text(event)

        await self._client.chat_postMessage(
            channel=channel,
            blocks=blocks,
            text=fallback_text,
        )

    def _build_blocks(
        self,
        event: NotificationEvent,
        target: NotificationTarget,
    ) -> list[dict[str, Any]]:
        """Build Slack Block Kit blocks.

        Resolution order:
        1. Custom template from CONFIG.md `template` field
        2. Event-type default template from workspace
        3. Built-in hardcoded Block Kit layout
        """
        if target.template and self._templates_dir:
            template_path = (self._templates_dir / f"{target.template}.json.j2").resolve()
            if not template_path.is_relative_to(self._templates_dir.resolve()):
                logger.warning("Template path traversal blocked: %s", target.template)
                return self._default_blocks(event)
            if template_path.exists():
                return self._render_template(template_path, event, target)

        if self._templates_dir:
            event_suffix = event.type.split(".")[-1]  # completed | failed | timeout
            event_template = (self._templates_dir / f"default-{event_suffix}.json.j2").resolve()
            if not event_template.is_relative_to(self._templates_dir.resolve()):
                return self._default_blocks(event)
            if event_template.exists():
                return self._render_template(event_template, event, target)

        return self._default_blocks(event)

    @staticmethod
    def _render_template(
        path: Path,
        event: NotificationEvent,
        target: NotificationTarget,
    ) -> list[dict[str, Any]]:
        """Render a Jinja2 Block Kit template."""
        from agent_gateway.notifications.template import render_template

        rendered = render_template(path, event=event, target=target)
        result: list[dict[str, Any]] = json.loads(rendered)
        return result

    def _default_blocks(self, event: NotificationEvent) -> list[dict[str, Any]]:
        """Professional default Block Kit layout."""
        emoji, status_text, _color = _STATUS_CONFIG.get(
            event.type, (":bell:", event.status, "#808080")
        )

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji}  Agent Execution {status_text}",
                    "emoji": True,
                },
            },
            {"type": "divider"},
        ]

        # Agent + Execution ID fields
        fields: list[dict[str, str]] = [
            {"type": "mrkdwn", "text": f"*Agent*\n`{event.agent_id}`"},
            {"type": "mrkdwn", "text": f"*Execution ID*\n`{event.execution_id}`"},
        ]

        if event.duration_ms:
            duration_s = event.duration_ms / 1000
            duration_str = f"{duration_s / 60:.1f}m" if duration_s >= 60 else f"{duration_s:.1f}s"
            fields.append({"type": "mrkdwn", "text": f"*Duration*\n{duration_str}"})

        if event.usage and event.usage.get("cost_usd"):
            fields.append(
                {"type": "mrkdwn", "text": f"*Cost*\n${event.usage['cost_usd']:.4f}"}
            )

        blocks.append({"type": "section", "fields": fields})

        # User message (truncated)
        if event.message:
            truncated = event.message[:300]
            if len(event.message) > 300:
                truncated += "..."
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*Input*\n>{truncated}"}}
            )

        # Result or Error
        if event.type == "execution.completed" and event.result:
            result_text = _format_result(event.result)
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Result*\n```{result_text}```"},
                }
            )
        elif event.error:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Error*\n```{event.error[:1000]}```"},
                }
            )

        # Footer with timestamp
        completed = event.completed_at or datetime.now(timezone.utc)
        ts = completed.strftime("%Y-%m-%d %H:%M:%S UTC")
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"agent-gateway | {ts}"}],
            }
        )

        return blocks

    @staticmethod
    def _build_fallback_text(event: NotificationEvent) -> str:
        """Plain-text fallback for notifications that don't support blocks."""
        return f"Agent '{event.agent_id}' execution {event.status}: {event.execution_id}"


def _format_result(result: dict[str, Any], max_len: int = 2000) -> str:
    """Format result dict as readable text, truncated to max_len."""
    text = json.dumps(result, indent=2, default=str)
    if len(text) > max_len:
        text = text[:max_len] + "\n... (truncated)"
    return text
