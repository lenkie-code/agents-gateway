"""Notification worker — consumes jobs from the notification queue."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agent_gateway.notifications.models import (
    AgentNotificationConfig,
    NotificationJob,
    build_notification_event,
    sanitize_target,
)

if TYPE_CHECKING:
    from agent_gateway.notifications.engine import NotificationEngine
    from agent_gateway.persistence.protocols import NotificationRepository

logger = logging.getLogger(__name__)

# Type alias for any notification queue backend
NotificationQueue = Any


class NotificationWorker:
    """Single consumer coroutine that dequeues and delivers notification jobs."""

    def __init__(
        self,
        queue: NotificationQueue,
        engine: NotificationEngine,
        notification_repo: NotificationRepository | None = None,
    ) -> None:
        self._queue = queue
        self._engine = engine
        self._notification_repo = notification_repo
        self._task: asyncio.Task[None] | None = None
        self._shutting_down = False

    async def start(self) -> None:
        self._task = asyncio.create_task(self._worker_loop(), name="notification-worker")
        logger.info("Notification worker started")

    async def drain(self) -> None:
        self._shutting_down = True
        if self._task is not None:
            # Give it a few seconds to finish current job
            done, pending = await asyncio.wait([self._task], timeout=10.0)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            self._task = None
        logger.info("Notification worker drained")

    async def _worker_loop(self) -> None:
        while not self._shutting_down:
            try:
                job = await self._queue.dequeue(timeout=1.0)
            except Exception:
                logger.warning("Notification worker: dequeue failed", exc_info=True)
                await asyncio.sleep(1.0)
                continue

            if job is None:
                continue

            await self._process_job(job)

    async def _process_job(self, job: NotificationJob) -> None:
        try:
            event = build_notification_event(
                execution_id=job.execution_id,
                agent_id=job.agent_id,
                status=job.status,
                message=job.message,
                result=job.result,
                error=job.error,
                usage=job.usage,
                duration_ms=job.duration_ms,
                input=job.input,
            )
            config = AgentNotificationConfig.from_dict(job.config)

            await self._engine.notify(event, config)
            await self._queue.ack(job.job_id)

            # Log successful delivery
            await self._log_delivery(
                event=event,
                config=config,
                status="delivered",
                attempts=1,
                last_error=None,
            )
        except Exception as exc:
            logger.warning(
                "Notification worker: job %s failed, nacking",
                job.job_id,
                exc_info=True,
            )
            await self._queue.nack(job.job_id)

            # Log failed delivery
            event = build_notification_event(
                execution_id=job.execution_id,
                agent_id=job.agent_id,
                status=job.status,
                message=job.message,
                result=job.result,
                error=job.error,
                usage=job.usage,
                duration_ms=job.duration_ms,
                input=job.input,
            )
            config = AgentNotificationConfig.from_dict(job.config)
            await self._log_delivery(
                event=event,
                config=config,
                status="failed",
                attempts=1,
                last_error=str(exc),
            )

    async def _log_delivery(
        self,
        *,
        event: Any,
        config: AgentNotificationConfig,
        status: str,
        attempts: int,
        last_error: str | None,
    ) -> None:
        """Persist delivery records for each notification target. Never raises."""
        if self._notification_repo is None:
            return

        from agent_gateway.notifications.models import NotificationTarget
        from agent_gateway.persistence.domain import NotificationDeliveryRecord

        # Resolve targets from config
        _event_routing: dict[str, str] = {
            "execution.completed": "on_complete",
            "execution.failed": "on_error",
            "execution.timeout": "on_timeout",
        }
        attr_name = _event_routing.get(event.type)
        if attr_name is None:
            return
        targets: list[NotificationTarget] = getattr(config, attr_name, [])

        now = datetime.now(UTC)
        for t in targets:
            try:
                record = NotificationDeliveryRecord(
                    execution_id=event.execution_id,
                    agent_id=event.agent_id,
                    event_type=event.type,
                    channel=t.channel,
                    target=sanitize_target(t.target or t.url or ""),
                    status=status,
                    attempts=attempts,
                    last_error=last_error,
                    created_at=now,
                    delivered_at=now if status == "delivered" else None,
                )
                await self._notification_repo.create(record)
            except Exception:
                logger.warning(
                    "Failed to log notification delivery for execution %s",
                    event.execution_id,
                    exc_info=True,
                )
