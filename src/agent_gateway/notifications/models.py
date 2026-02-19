"""Notification domain models — plain dataclasses with zero optional-dependency imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NotificationEvent:
    """Immutable event fired when an execution reaches a terminal state."""

    type: str  # execution.completed | execution.failed | execution.timeout
    execution_id: str
    agent_id: str
    status: str
    message: str  # the original user message
    result: dict[str, Any] | None = None
    error: str | None = None
    usage: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int = 0
    context: dict[str, Any] | None = None


@dataclass(frozen=True)
class NotificationTarget:
    """A single notification destination parsed from agent CONFIG.md.

    For Slack:
      - target: "#channel-name"
      - template: optional custom Block Kit template name

    For Webhook (two modes):
      - target: "crm-integration"  → references a globally registered endpoint
      - url: "https://..."         → inline endpoint, no global registration needed
        secret: optional HMAC secret
        payload_template: optional inline Jinja2 template
    """

    channel: str  # "slack" | "webhook"
    target: str = ""  # Slack channel or global webhook name
    template: str | None = None  # Slack Block Kit template name
    url: str | None = None  # Inline webhook URL (per-agent)
    secret: str | None = None  # Inline webhook HMAC secret (per-agent)
    payload_template: str | None = None  # Inline webhook Jinja2 payload (per-agent)


@dataclass
class AgentNotificationConfig:
    """Per-agent notification rules, parsed from CONFIG.md frontmatter."""

    on_complete: list[NotificationTarget] = field(default_factory=list)
    on_error: list[NotificationTarget] = field(default_factory=list)
    on_timeout: list[NotificationTarget] = field(default_factory=list)
