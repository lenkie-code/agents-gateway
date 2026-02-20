"""Outbound notification system — pluggable backends for Slack, webhooks, etc."""

from agent_gateway.notifications.engine import NotificationEngine
from agent_gateway.notifications.models import (
    AgentNotificationConfig,
    NotificationEvent,
    NotificationJob,
    NotificationTarget,
)
from agent_gateway.notifications.protocols import NotificationBackend
from agent_gateway.notifications.worker import NotificationWorker

__all__ = [
    "AgentNotificationConfig",
    "NotificationBackend",
    "NotificationEngine",
    "NotificationEvent",
    "NotificationJob",
    "NotificationTarget",
    "NotificationWorker",
]
