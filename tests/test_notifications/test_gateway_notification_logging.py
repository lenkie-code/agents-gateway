"""Tests for gateway-level notification delivery logging.

Covers fire_notifications direct-dispatch path, _notify_and_log,
and NotificationWorker delivery logging.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from agent_gateway.notifications.engine import NotificationEngine
from agent_gateway.notifications.models import (
    AgentNotificationConfig,
    NotificationTarget,
)
from agent_gateway.persistence.domain import NotificationDeliveryRecord


class FakeNotificationRepo:
    """In-memory notification repository for testing."""

    def __init__(self) -> None:
        self.records: list[NotificationDeliveryRecord] = []

    async def create(self, record: NotificationDeliveryRecord) -> None:
        self.records.append(record)

    async def list_recent(self, **kwargs) -> list[NotificationDeliveryRecord]:  # type: ignore[override]
        return self.records

    async def count(self, **kwargs) -> int:  # type: ignore[override]
        return len(self.records)

    async def get(self, record_id: int) -> NotificationDeliveryRecord | None:
        for r in self.records:
            if r.id == record_id:
                return r
        return None

    async def update_status(self, record_id: int, **kwargs) -> None:  # type: ignore[override]
        pass


class TestDirectDispatchLogging:
    """Tests for fire_notifications on the direct (no-queue) path."""

    async def test_notify_and_log_success(self) -> None:
        """_notify_and_log creates delivered records on success."""
        repo = FakeNotificationRepo()
        target = NotificationTarget(channel="webhook", target="my-hook")

        engine = NotificationEngine()
        backend = AsyncMock()
        backend.channel = "webhook"
        engine.register(backend)

        from agent_gateway.gateway import Gateway
        from agent_gateway.notifications.models import build_notification_event

        gw = MagicMock(spec=Gateway)
        gw._notification_engine = engine
        gw._notification_repo = repo
        gw._background_tasks = set()

        # Bind real methods
        gw._notify_and_log = Gateway._notify_and_log.__get__(gw, Gateway)
        gw._log_notification_delivery = Gateway._log_notification_delivery.__get__(gw, Gateway)
        gw._persist_notification_record = Gateway._persist_notification_record.__get__(gw, Gateway)

        event = build_notification_event(
            execution_id="exec-1",
            agent_id="agent-1",
            status="completed",
            message="test",
        )
        await gw._notify_and_log(
            event, config=None, execution_id="exec-1", agent_id="agent-1", targets=[target]
        )

        # Wait for background persist tasks
        if gw._background_tasks:
            await asyncio.gather(*gw._background_tasks, return_exceptions=True)

        assert len(repo.records) == 1
        assert repo.records[0].status == "delivered"
        assert repo.records[0].execution_id == "exec-1"
        assert repo.records[0].channel == "webhook"
        assert repo.records[0].target == "my-hook"
        assert repo.records[0].attempts == 1
        assert repo.records[0].delivered_at is not None

    async def test_notify_and_log_failure(self) -> None:
        """_notify_and_log creates failed records when notify() raises."""
        repo = FakeNotificationRepo()
        target = NotificationTarget(channel="webhook", target="my-hook")

        # Use a mock engine that raises (simulating an unexpected error)
        engine = AsyncMock()
        engine.notify = AsyncMock(side_effect=RuntimeError("connection refused"))

        from agent_gateway.gateway import Gateway
        from agent_gateway.notifications.models import build_notification_event

        gw = MagicMock(spec=Gateway)
        gw._notification_engine = engine
        gw._notification_repo = repo
        gw._background_tasks = set()
        gw._notify_and_log = Gateway._notify_and_log.__get__(gw, Gateway)
        gw._log_notification_delivery = Gateway._log_notification_delivery.__get__(gw, Gateway)
        gw._persist_notification_record = Gateway._persist_notification_record.__get__(gw, Gateway)

        event = build_notification_event(
            execution_id="exec-2",
            agent_id="agent-2",
            status="failed",
            message="test",
        )
        await gw._notify_and_log(
            event,
            config=AgentNotificationConfig(on_error=[target]),
            execution_id="exec-2",
            agent_id="agent-2",
            targets=[target],
        )

        if gw._background_tasks:
            await asyncio.gather(*gw._background_tasks, return_exceptions=True)

        assert len(repo.records) == 1
        assert repo.records[0].status == "failed"
        assert repo.records[0].last_error is not None
        assert "connection refused" in repo.records[0].last_error

    async def test_notify_and_log_does_not_raise(self) -> None:
        """_notify_and_log never propagates exceptions (fire-and-forget)."""
        engine = AsyncMock()
        engine.notify = AsyncMock(side_effect=RuntimeError("boom"))

        from agent_gateway.gateway import Gateway
        from agent_gateway.notifications.models import build_notification_event

        # Repo that also fails
        broken_repo = AsyncMock()
        broken_repo.create = AsyncMock(side_effect=RuntimeError("db down"))

        gw = MagicMock(spec=Gateway)
        gw._notification_engine = engine
        gw._notification_repo = broken_repo
        gw._background_tasks = set()
        gw._notify_and_log = Gateway._notify_and_log.__get__(gw, Gateway)
        gw._log_notification_delivery = Gateway._log_notification_delivery.__get__(gw, Gateway)
        gw._persist_notification_record = Gateway._persist_notification_record.__get__(gw, Gateway)

        target = NotificationTarget(channel="webhook", target="hook")
        event = build_notification_event(
            execution_id="exec-3",
            agent_id="agent-3",
            status="failed",
            message="test",
        )

        # Should not raise even with broken engine + broken repo
        await gw._notify_and_log(
            event,
            config=AgentNotificationConfig(on_error=[target]),
            execution_id="exec-3",
            agent_id="agent-3",
            targets=[target],
        )

        if gw._background_tasks:
            await asyncio.gather(*gw._background_tasks, return_exceptions=True)

    async def test_no_records_for_no_targets(self) -> None:
        """No delivery records when there are no notification targets."""
        repo = FakeNotificationRepo()

        from agent_gateway.gateway import Gateway
        from agent_gateway.notifications.models import build_notification_event

        engine = NotificationEngine()
        gw = MagicMock(spec=Gateway)
        gw._notification_engine = engine
        gw._notification_repo = repo
        gw._background_tasks = set()
        gw._notify_and_log = Gateway._notify_and_log.__get__(gw, Gateway)
        gw._log_notification_delivery = Gateway._log_notification_delivery.__get__(gw, Gateway)
        gw._persist_notification_record = Gateway._persist_notification_record.__get__(gw, Gateway)

        event = build_notification_event(
            execution_id="exec-4",
            agent_id="agent-4",
            status="completed",
            message="test",
        )
        await gw._notify_and_log(
            event,
            config=AgentNotificationConfig(),
            execution_id="exec-4",
            agent_id="agent-4",
            targets=[],
        )

        if gw._background_tasks:
            await asyncio.gather(*gw._background_tasks, return_exceptions=True)

        assert len(repo.records) == 0

    async def test_multiple_targets_create_multiple_records(self) -> None:
        """Each notification target gets its own delivery record."""
        repo = FakeNotificationRepo()
        targets = [
            NotificationTarget(channel="webhook", target="hook-1"),
            NotificationTarget(channel="slack", target="#alerts"),
        ]

        engine = NotificationEngine()
        for chan in ("webhook", "slack"):
            backend = AsyncMock()
            backend.channel = chan
            engine.register(backend)

        from agent_gateway.gateway import Gateway
        from agent_gateway.notifications.models import build_notification_event

        gw = MagicMock(spec=Gateway)
        gw._notification_engine = engine
        gw._notification_repo = repo
        gw._background_tasks = set()
        gw._notify_and_log = Gateway._notify_and_log.__get__(gw, Gateway)
        gw._log_notification_delivery = Gateway._log_notification_delivery.__get__(gw, Gateway)
        gw._persist_notification_record = Gateway._persist_notification_record.__get__(gw, Gateway)

        event = build_notification_event(
            execution_id="exec-5",
            agent_id="agent-5",
            status="completed",
            message="test",
        )
        await gw._notify_and_log(
            event, config=None, execution_id="exec-5", agent_id="agent-5", targets=targets
        )

        if gw._background_tasks:
            await asyncio.gather(*gw._background_tasks, return_exceptions=True)

        assert len(repo.records) == 2
        channels = {r.channel for r in repo.records}
        assert channels == {"webhook", "slack"}


class TestWorkerDeliveryLogging:
    """Tests for NotificationWorker delivery logging."""

    async def test_worker_logs_delivered_on_success(self) -> None:
        """Worker creates 'delivered' record after successful processing."""
        from agent_gateway.notifications.models import NotificationJob
        from agent_gateway.notifications.worker import NotificationWorker

        repo = FakeNotificationRepo()
        engine = AsyncMock()
        engine.notify = AsyncMock()
        queue = AsyncMock()

        config = AgentNotificationConfig(
            on_complete=[NotificationTarget(channel="webhook", target="hook")]
        )
        job = NotificationJob(
            job_id="job-1",
            execution_id="exec-w1",
            agent_id="agent-w1",
            status="completed",
            message="hello",
            config=config.to_dict(),
        )

        worker = NotificationWorker(queue=queue, engine=engine, notification_repo=repo)
        await worker._process_job(job)

        queue.ack.assert_called_once_with("job-1")
        assert len(repo.records) == 1
        assert repo.records[0].status == "delivered"
        assert repo.records[0].execution_id == "exec-w1"

    async def test_worker_logs_failed_on_error(self) -> None:
        """Worker creates 'failed' record when engine.notify() raises."""
        from agent_gateway.notifications.models import NotificationJob
        from agent_gateway.notifications.worker import NotificationWorker

        repo = FakeNotificationRepo()
        engine = AsyncMock()
        engine.notify = AsyncMock(side_effect=RuntimeError("send failed"))
        queue = AsyncMock()

        config = AgentNotificationConfig(
            on_error=[NotificationTarget(channel="slack", target="#alerts")]
        )
        job = NotificationJob(
            job_id="job-2",
            execution_id="exec-w2",
            agent_id="agent-w2",
            status="failed",
            message="error occurred",
            config=config.to_dict(),
        )

        worker = NotificationWorker(queue=queue, engine=engine, notification_repo=repo)
        await worker._process_job(job)

        queue.nack.assert_called_once_with("job-2")
        assert len(repo.records) == 1
        assert repo.records[0].status == "failed"
        assert "send failed" in (repo.records[0].last_error or "")

    async def test_worker_no_repo_no_error(self) -> None:
        """Worker with no repo does not error on logging."""
        from agent_gateway.notifications.models import NotificationJob
        from agent_gateway.notifications.worker import NotificationWorker

        engine = AsyncMock()
        engine.notify = AsyncMock()
        queue = AsyncMock()

        config = AgentNotificationConfig(
            on_complete=[NotificationTarget(channel="webhook", target="hook")]
        )
        job = NotificationJob(
            job_id="job-3",
            execution_id="exec-w3",
            agent_id="agent-w3",
            status="completed",
            message="hello",
            config=config.to_dict(),
        )

        worker = NotificationWorker(queue=queue, engine=engine, notification_repo=None)
        await worker._process_job(job)
        queue.ack.assert_called_once_with("job-3")
