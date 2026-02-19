"""Tests for the notification engine — dispatch, retry, and error isolation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from agent_gateway.notifications.engine import BACKOFF_BASE_S, MAX_RETRIES, NotificationEngine
from agent_gateway.notifications.models import (
    AgentNotificationConfig,
    NotificationEvent,
    NotificationTarget,
)


def _make_event(
    event_type: str = "execution.completed",
    status: str = "completed",
) -> NotificationEvent:
    return NotificationEvent(
        type=event_type,
        execution_id="exec-123",
        agent_id="test-agent",
        status=status,
        message="Hello world",
        duration_ms=1500,
        completed_at=datetime.now(UTC),
    )


def _make_backend(channel: str = "webhook") -> AsyncMock:
    backend = AsyncMock()
    backend.channel = channel
    backend.initialize = AsyncMock()
    backend.dispose = AsyncMock()
    backend.send = AsyncMock()
    return backend


class TestNotificationEngine:
    async def test_no_backends_registered(self) -> None:
        engine = NotificationEngine()
        assert engine.has_backends is False

    async def test_register_backend(self) -> None:
        engine = NotificationEngine()
        backend = _make_backend("slack")
        engine.register(backend)
        assert engine.has_backends is True

    async def test_initialize_all_backends(self) -> None:
        engine = NotificationEngine()
        b1 = _make_backend("slack")
        b2 = _make_backend("webhook")
        engine.register(b1)
        engine.register(b2)

        await engine.initialize()

        b1.initialize.assert_awaited_once()
        b2.initialize.assert_awaited_once()

    async def test_dispose_all_backends(self) -> None:
        engine = NotificationEngine()
        b1 = _make_backend("slack")
        b2 = _make_backend("webhook")
        engine.register(b1)
        engine.register(b2)

        await engine.dispose()

        b1.dispose.assert_awaited_once()
        b2.dispose.assert_awaited_once()

    async def test_dispose_swallows_errors(self) -> None:
        engine = NotificationEngine()
        backend = _make_backend("webhook")
        backend.dispose.side_effect = RuntimeError("boom")
        engine.register(backend)

        # Should not raise
        await engine.dispose()

    async def test_dispatch_on_complete(self) -> None:
        engine = NotificationEngine()
        backend = _make_backend("webhook")
        engine.register(backend)

        event = _make_event("execution.completed")
        config = AgentNotificationConfig(
            on_complete=[NotificationTarget(channel="webhook", url="https://example.com/hook")],
        )

        await engine.notify(event, config)

        backend.send.assert_awaited_once()
        call_args = backend.send.call_args
        assert call_args[0][0] is event
        assert call_args[0][1].url == "https://example.com/hook"

    async def test_dispatch_on_error(self) -> None:
        engine = NotificationEngine()
        backend = _make_backend("webhook")
        engine.register(backend)

        event = _make_event("execution.failed", status="failed")
        config = AgentNotificationConfig(
            on_error=[NotificationTarget(channel="webhook", url="https://example.com/hook")],
        )

        await engine.notify(event, config)
        backend.send.assert_awaited_once()

    async def test_dispatch_on_timeout(self) -> None:
        engine = NotificationEngine()
        backend = _make_backend("webhook")
        engine.register(backend)

        event = _make_event("execution.timeout", status="timeout")
        config = AgentNotificationConfig(
            on_timeout=[NotificationTarget(channel="webhook", url="https://example.com/hook")],
        )

        await engine.notify(event, config)
        backend.send.assert_awaited_once()

    async def test_no_targets_for_event_type(self) -> None:
        engine = NotificationEngine()
        backend = _make_backend("webhook")
        engine.register(backend)

        event = _make_event("execution.completed")
        config = AgentNotificationConfig()  # no targets at all

        await engine.notify(event, config)
        backend.send.assert_not_awaited()

    async def test_unknown_event_type_ignored(self) -> None:
        engine = NotificationEngine()
        backend = _make_backend("webhook")
        engine.register(backend)

        event = _make_event("execution.custom_unknown")
        config = AgentNotificationConfig(
            on_complete=[NotificationTarget(channel="webhook", url="https://example.com/hook")],
        )

        await engine.notify(event, config)
        backend.send.assert_not_awaited()

    async def test_missing_backend_for_channel_logged(self) -> None:
        """If no backend is registered for a target's channel, skip silently."""
        engine = NotificationEngine()
        # No backends registered

        event = _make_event("execution.completed")
        config = AgentNotificationConfig(
            on_complete=[NotificationTarget(channel="webhook", url="https://example.com/hook")],
        )

        # Should not raise
        await engine.notify(event, config)

    async def test_multiple_targets_dispatched(self) -> None:
        engine = NotificationEngine()
        slack_backend = _make_backend("slack")
        webhook_backend = _make_backend("webhook")
        engine.register(slack_backend)
        engine.register(webhook_backend)

        event = _make_event("execution.completed")
        config = AgentNotificationConfig(
            on_complete=[
                NotificationTarget(channel="slack", target="#alerts"),
                NotificationTarget(channel="webhook", url="https://example.com/hook"),
            ],
        )

        await engine.notify(event, config)

        slack_backend.send.assert_awaited_once()
        webhook_backend.send.assert_awaited_once()

    async def test_retry_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Backend send fails twice then succeeds on third attempt."""
        # Speed up retries for test
        monkeypatch.setattr("agent_gateway.notifications.engine.BACKOFF_BASE_S", 0.01)

        engine = NotificationEngine()
        backend = _make_backend("webhook")
        backend.send.side_effect = [
            RuntimeError("fail 1"),
            RuntimeError("fail 2"),
            None,  # success on third attempt
        ]
        engine.register(backend)

        event = _make_event("execution.completed")
        config = AgentNotificationConfig(
            on_complete=[NotificationTarget(channel="webhook", url="https://example.com/hook")],
        )

        await engine.notify(event, config)

        assert backend.send.await_count == 3

    async def test_retry_exhausted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """After MAX_RETRIES failures, notification is abandoned (no raise)."""
        monkeypatch.setattr("agent_gateway.notifications.engine.BACKOFF_BASE_S", 0.01)

        engine = NotificationEngine()
        backend = _make_backend("webhook")
        backend.send.side_effect = RuntimeError("always fails")
        engine.register(backend)

        event = _make_event("execution.completed")
        config = AgentNotificationConfig(
            on_complete=[NotificationTarget(channel="webhook", url="https://example.com/hook")],
        )

        # Should not raise
        await engine.notify(event, config)

        assert backend.send.await_count == MAX_RETRIES

    async def test_one_target_failure_does_not_block_others(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If one target fails, others still get notified."""
        monkeypatch.setattr("agent_gateway.notifications.engine.BACKOFF_BASE_S", 0.01)

        engine = NotificationEngine()
        failing_backend = _make_backend("webhook")
        failing_backend.send.side_effect = RuntimeError("webhook down")

        working_backend = _make_backend("slack")
        engine.register(failing_backend)
        engine.register(working_backend)

        event = _make_event("execution.completed")
        config = AgentNotificationConfig(
            on_complete=[
                NotificationTarget(channel="webhook", url="https://broken.com"),
                NotificationTarget(channel="slack", target="#alerts"),
            ],
        )

        await engine.notify(event, config)

        # Slack should have succeeded
        working_backend.send.assert_awaited_once()
        # Webhook should have retried and failed
        assert failing_backend.send.await_count == MAX_RETRIES
