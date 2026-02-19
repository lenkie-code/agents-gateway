"""Notification engine — dispatches notifications to registered backends."""

from __future__ import annotations

import asyncio
import logging

from agent_gateway.notifications.models import (
    AgentNotificationConfig,
    NotificationEvent,
    NotificationTarget,
)
from agent_gateway.notifications.protocols import NotificationBackend

logger = logging.getLogger(__name__)

# Maps event type → config attribute name
_EVENT_ROUTING: dict[str, str] = {
    "execution.completed": "on_complete",
    "execution.failed": "on_error",
    "execution.timeout": "on_timeout",
}

MAX_RETRIES = 3
BACKOFF_BASE_S = 1.0  # 1s, 2s, 4s


class NotificationEngine:
    """Dispatches notifications to registered backends. Fire-and-forget."""

    def __init__(self) -> None:
        self._backends: dict[str, NotificationBackend] = {}

    def register(self, backend: NotificationBackend) -> None:
        """Register a notification backend for a channel."""
        self._backends[backend.channel] = backend

    @property
    def has_backends(self) -> bool:
        """Whether any notification backends are registered."""
        return bool(self._backends)

    async def initialize(self) -> None:
        """Initialize all registered backends."""
        for backend in self._backends.values():
            await backend.initialize()

    async def dispose(self) -> None:
        """Dispose all registered backends."""
        for backend in self._backends.values():
            try:
                await backend.dispose()
            except Exception:
                logger.warning(
                    "Failed to dispose %s backend", backend.channel, exc_info=True
                )

    async def notify(
        self,
        event: NotificationEvent,
        config: AgentNotificationConfig,
    ) -> None:
        """Dispatch notifications for an event. Fire-and-forget.

        Never raises — all errors are logged and swallowed.
        """
        attr_name = _EVENT_ROUTING.get(event.type)
        if attr_name is None:
            return

        targets: list[NotificationTarget] = getattr(config, attr_name, [])
        if not targets:
            return

        tasks = [
            asyncio.create_task(self._send_with_retry(event, t)) for t in targets
        ]
        # Gather but swallow all exceptions
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_with_retry(
        self,
        event: NotificationEvent,
        target: NotificationTarget,
    ) -> None:
        """Send a single notification with exponential backoff retries."""
        backend = self._backends.get(target.channel)
        if backend is None:
            logger.warning(
                "No backend registered for channel %r (target: %s)",
                target.channel,
                target.target or target.url,
            )
            return

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                await backend.send(event, target)
                return
            except Exception as exc:
                last_exc = exc
                wait = BACKOFF_BASE_S * (2**attempt)
                logger.warning(
                    "Notification to %s/%s failed (attempt %d/%d), retrying in %.1fs: %s",
                    target.channel,
                    target.target or target.url,
                    attempt + 1,
                    MAX_RETRIES,
                    wait,
                    exc,
                )
                await asyncio.sleep(wait)

        logger.error(
            "Notification to %s/%s failed after %d attempts: %s",
            target.channel,
            target.target or target.url,
            MAX_RETRIES,
            last_exc,
        )
