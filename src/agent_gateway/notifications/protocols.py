"""Notification backend protocol — structural typing, no inheritance required."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_gateway.notifications.models import NotificationEvent, NotificationTarget


@runtime_checkable
class NotificationBackend(Protocol):
    """Contract for a pluggable notification backend."""

    @property
    def channel(self) -> str:
        """The channel identifier this backend handles (e.g. 'slack', 'webhook')."""
        ...

    async def initialize(self) -> None:
        """Validate config, establish connections. Idempotent."""
        ...

    async def dispose(self) -> None:
        """Close connections and release resources."""
        ...

    async def send(
        self,
        event: NotificationEvent,
        target: NotificationTarget,
    ) -> None:
        """Send a notification. Raise on failure (engine handles retries)."""
        ...
