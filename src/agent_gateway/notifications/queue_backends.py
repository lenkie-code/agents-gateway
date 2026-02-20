"""Notification queue backends — lightweight queues for NotificationJob.

Mirrors the execution queue backends but typed for NotificationJob and
without cancel semantics. Protocol: initialize, dispose, enqueue, dequeue, ack, nack.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_gateway.notifications.models import NotificationJob

logger = logging.getLogger(__name__)


class MemoryNotificationQueue:
    """In-process asyncio.Queue for notification jobs. Dev/testing only."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[NotificationJob] = asyncio.Queue()

    async def initialize(self) -> None:
        pass

    async def dispose(self) -> None:
        pass

    async def enqueue(self, job: NotificationJob) -> None:
        await self._queue.put(job)

    async def dequeue(self, timeout: float = 0) -> NotificationJob | None:  # noqa: ASYNC109
        try:
            if timeout <= 0:
                return self._queue.get_nowait()
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except (asyncio.QueueEmpty, TimeoutError):
            return None

    async def ack(self, job_id: str) -> None:
        pass

    async def nack(self, job_id: str) -> None:
        pass

    async def length(self) -> int:
        return self._queue.qsize()


class RedisNotificationQueue:
    """Redis Streams notification queue.

    Requires: pip install agent-gateway[redis]
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        stream_key: str = "ag:notifications",
        consumer_group: str = "ag-notification-workers",
    ) -> None:
        self._url = url
        self._stream_key = stream_key
        self._consumer_group = consumer_group
        self._consumer_name: str = ""
        self._redis: Any = None

    async def initialize(self) -> None:
        import uuid

        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(self._url, decode_responses=True)
        self._consumer_name = f"notif-worker-{uuid.uuid4().hex[:8]}"

        try:
            await self._redis.xgroup_create(
                self._stream_key, self._consumer_group, id="0", mkstream=True
            )
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                raise

        logger.info(
            "RedisNotificationQueue initialized: stream=%s, group=%s",
            self._stream_key,
            self._consumer_group,
        )

    async def dispose(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def enqueue(self, job: NotificationJob) -> None:
        if self._redis is None:
            raise RuntimeError("RedisNotificationQueue not initialized")
        await self._redis.xadd(self._stream_key, {"job": job.to_json()}, id="*")

    async def dequeue(self, timeout: float = 0) -> NotificationJob | None:  # noqa: ASYNC109
        if self._redis is None:
            return None

        block_ms = int(timeout * 1000) if timeout > 0 else None
        results = await self._redis.xreadgroup(
            self._consumer_group,
            self._consumer_name,
            {self._stream_key: ">"},
            count=1,
            block=block_ms,
        )

        if not results:
            return None

        for _stream, messages in results:
            for msg_id, fields in messages:
                job_data = fields.get("job")
                if job_data is None:
                    await self._redis.xack(self._stream_key, self._consumer_group, msg_id)
                    continue

                job = NotificationJob.from_json(job_data)
                # Store msg_id mapping for ack/nack
                await self._redis.hset(
                    f"ag:notif_msg_map:{job.job_id}", mapping={"msg_id": msg_id}
                )
                return job

        return None

    async def ack(self, job_id: str) -> None:
        if self._redis is None:
            return
        msg_id = await self._redis.hget(f"ag:notif_msg_map:{job_id}", "msg_id")
        if msg_id:
            await self._redis.xack(self._stream_key, self._consumer_group, msg_id)
            await self._redis.delete(f"ag:notif_msg_map:{job_id}")

    async def nack(self, job_id: str) -> None:
        if self._redis is None:
            return
        # Don't ack — PEL handles re-delivery after visibility timeout
        await self._redis.delete(f"ag:notif_msg_map:{job_id}")

    async def length(self) -> int:
        if self._redis is None:
            return 0
        return int(await self._redis.xlen(self._stream_key))


class RabbitMQNotificationQueue:
    """RabbitMQ notification queue.

    Requires: pip install agent-gateway[rabbitmq]
    """

    def __init__(
        self,
        url: str = "amqp://guest:guest@localhost:5672/",
        queue_name: str = "ag.notifications",
    ) -> None:
        self._url = url
        self._queue_name = queue_name
        self._connection: Any = None
        self._channel: Any = None
        self._queue: Any = None
        self._pending_messages: dict[str, Any] = {}

    async def initialize(self) -> None:
        import aio_pika

        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=1)

        self._queue = await self._channel.declare_queue(
            self._queue_name, durable=True
        )

        logger.info("RabbitMQNotificationQueue initialized: queue=%s", self._queue_name)

    async def dispose(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            self._channel = None
            self._queue = None
        self._pending_messages.clear()

    async def enqueue(self, job: NotificationJob) -> None:
        if self._channel is None:
            raise RuntimeError("RabbitMQNotificationQueue not initialized")
        import aio_pika

        message = aio_pika.Message(
            body=job.to_json().encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=job.job_id,
        )
        await self._channel.default_exchange.publish(message, routing_key=self._queue_name)

    async def dequeue(self, timeout: float = 0) -> NotificationJob | None:  # noqa: ASYNC109
        if self._queue is None:
            return None

        message = await self._queue.get(fail=False, timeout=timeout or 1)
        if message is None:
            return None

        try:
            job = NotificationJob.from_json(message.body.decode("utf-8"))
            self._pending_messages[job.job_id] = message
            return job
        except Exception:
            await message.reject(requeue=False)
            return None

    async def ack(self, job_id: str) -> None:
        message = self._pending_messages.pop(job_id, None)
        if message is not None:
            await message.ack()

    async def nack(self, job_id: str) -> None:
        message = self._pending_messages.pop(job_id, None)
        if message is not None:
            await message.reject(requeue=True)

    async def length(self) -> int:
        if self._queue is None or self._channel is None:
            return 0
        try:
            queue_info = await self._channel.declare_queue(self._queue_name, passive=True)
            return int(queue_info.declaration_result.message_count)
        except Exception:
            return 0
