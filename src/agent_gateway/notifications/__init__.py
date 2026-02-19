"""Outbound notification system — pluggable backends for Slack, webhooks, etc."""

from agent_gateway.notifications.engine import NotificationEngine
from agent_gateway.notifications.models import (
    AgentNotificationConfig,
    NotificationEvent,
    NotificationTarget,
)
from agent_gateway.notifications.protocols import NotificationBackend

__all__ = [
    "AgentNotificationConfig",
    "NotificationBackend",
    "NotificationEngine",
    "NotificationEvent",
    "NotificationTarget",
]
