"""Celery worker for agents-gateway.

Runs agent execution jobs dispatched by the gateway API.  A persistent
background event loop lives in a daemon thread so that all async gateway
code (engine, persistence, notifications) shares a single asyncio event
loop for the lifetime of each worker process.

Start with::

    celery -A worker worker -l info --pool=solo -Q agents_gateway

The ``--pool=solo`` flag is required because Celery's default prefork pool
does not play well with a persistent asyncio event loop — use one worker
process per CPU core instead::

    celery -A worker worker -l info --pool=solo --concurrency=1
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from datetime import UTC, datetime
from typing import Any

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery application
# ---------------------------------------------------------------------------

BROKER_URL = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672/")

celery = Celery("agents_gateway", broker=BROKER_URL)
celery.conf.task_serializer = "json"
celery.conf.accept_content = ["json"]
celery.conf.task_ignore_result = True
celery.conf.worker_send_task_events = True
celery.conf.task_send_sent_event = True
# Disable AMQP heartbeat — the default (60s) causes BrokenPipeError when the
# worker is busy running a long agent task and can't service the heartbeat.
celery.conf.broker_heartbeat = 0
# Restart worker after N tasks to prevent async resource accumulation.
# Default 10 in dev (keeps Flower happy); set to 1 in production for strictest isolation.
celery.conf.worker_max_tasks_per_child = int(os.getenv("CELERY_MAX_TASKS_PER_CHILD", "10"))
celery.conf.task_time_limit = int(os.getenv("CELERY_TASK_TIME_LIMIT", "7200"))  # 2h hard
celery.conf.task_soft_time_limit = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "6900"))

# ---------------------------------------------------------------------------
# Persistent event loop — shared across all tasks in a worker process
# ---------------------------------------------------------------------------

_bg_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
_bg_thread: threading.Thread | None = None
_bg_lock = threading.Lock()


def _ensure_loop_running() -> asyncio.AbstractEventLoop:
    """Start the background event loop thread on first call."""
    global _bg_thread
    with _bg_lock:
        if _bg_thread is None or not _bg_thread.is_alive():
            _bg_thread = threading.Thread(
                target=_bg_loop.run_forever, name="ag-event-loop", daemon=True
            )
            _bg_thread.start()
            logger.info("Background asyncio event loop started")
    return _bg_loop


def _run(coro: Any, timeout: float = 3600.0) -> Any:
    """Submit *coro* to the persistent event loop and block until it completes."""
    loop = _ensure_loop_running()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


# ---------------------------------------------------------------------------
# Gateway singleton — initialized once per worker process
# ---------------------------------------------------------------------------

_gw: Any = None  # agents_gateway.Gateway
_gw_init_lock = threading.Lock()


async def _init_gateway_async() -> Any:
    """Initialize and return the Gateway instance (runs on the bg event loop)."""
    global _gw
    if _gw is not None:
        return _gw

    logger.info("Initializing Gateway for Celery worker...")

    # Import app.py to reuse the same gateway configuration (workspace path,
    # webhook endpoint, API keys, etc.).  The module-level code constructs the
    # Gateway object but does NOT start it (no FastAPI lifespan).
    from app import gw as _app_gw  # noqa: PLC0415

    await _app_gw._startup()
    _gw = _app_gw

    logger.info("Gateway initialized: workspace=%s", _gw._workspace_path)
    return _gw


def _get_gateway() -> Any:
    """Return the lazily-initialized Gateway (blocking, for use from Celery task thread).

    Uses double-checked locking to ensure _startup() is called only once.
    Must NOT be called from inside the bg event loop — use ``_init_gateway_async``
    directly when already on the loop.
    """
    if _gw is not None:
        return _gw

    with _gw_init_lock:
        if _gw is not None:
            return _gw
        return _run(_init_gateway_async())


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery.task(
    name="agents_gateway.run_agent_execution",
    bind=True,
    max_retries=0,  # agent errors should surface as failed executions, not retries
)
def run_agent_execution(self: Any, job_data: dict[str, Any]) -> dict[str, Any]:
    """Execute an agent job dispatched by the gateway API.

    Args:
        job_data: Serialised :class:`~agent_gateway.queue.models.ExecutionJob` dict.

    Returns:
        A summary dict (``execution_id``, ``status``, ``duration_ms``).
    """
    return _run(_execute_job(job_data), timeout=float(celery.conf.task_time_limit))


async def _execute_job(job_data: dict[str, Any]) -> dict[str, Any]:
    """Async implementation of agent job execution."""
    from agent_gateway.engine.models import (
        ExecutionHandle,
        ExecutionOptions,
        ExecutionStatus,
        StopReason,
    )
    from agent_gateway.queue.models import ExecutionJob
    from agent_gateway.tools.runner import execute_tool

    gw = await _init_gateway_async()
    job = ExecutionJob(**job_data)

    logger.info("Worker executing job %s (agent=%s)", job.execution_id, job.agent_id)

    snapshot = gw._snapshot
    if snapshot is None or snapshot.engine is None:
        raise RuntimeError("Gateway not initialized — snapshot is None")

    agent = snapshot.workspace.agents.get(job.agent_id)
    if agent is None:
        await gw._execution_repo.update_status(
            job.execution_id,
            ExecutionStatus.FAILED,
            error=f"Agent '{job.agent_id}' not found",
        )
        logger.error("Agent '%s' not found in workspace", job.agent_id)
        return {"execution_id": job.execution_id, "status": "failed", "duration_ms": 0}

    # Mark as running
    await gw._execution_repo.update_status(job.execution_id, ExecutionStatus.RUNNING)

    handle = ExecutionHandle(job.execution_id)
    gw._execution_handles[job.execution_id] = handle

    exec_options = ExecutionOptions(
        timeout_ms=job.timeout_ms,
        output_schema=job.output_schema,
    )

    start = time.monotonic()
    notify_args: dict[str, Any] | None = None

    try:
        result = await snapshot.engine.execute(
            agent=agent,
            message=job.message,
            workspace=snapshot.workspace,
            input=job.input,
            options=exec_options,
            handle=handle,
            tool_executor=execute_tool,
        )

        duration_ms = int((time.monotonic() - start) * 1000)
        _stop_map = {
            StopReason.COMPLETED: ExecutionStatus.COMPLETED,
            StopReason.CANCELLED: ExecutionStatus.CANCELLED,
            StopReason.TIMEOUT: ExecutionStatus.TIMEOUT,
            StopReason.ERROR: ExecutionStatus.FAILED,
            StopReason.MAX_ITERATIONS: ExecutionStatus.COMPLETED,
            StopReason.MAX_TOOL_CALLS: ExecutionStatus.COMPLETED,
        }
        status = _stop_map.get(result.stop_reason, ExecutionStatus.FAILED)

        await gw._execution_repo.update_status(
            job.execution_id, status, completed_at=datetime.now(UTC)
        )
        await gw._execution_repo.update_result(
            job.execution_id,
            result=result.to_dict(),
            usage=result.usage.to_dict(),
        )

        logger.info(
            "Job %s completed: status=%s duration_ms=%d",
            job.execution_id,
            status.value,
            duration_ms,
        )

        notify_args = {
            "execution_id": job.execution_id,
            "agent_id": agent.id,
            "status": status.value,
            "message": job.message,
            "config": agent.notifications,
            "result": result.to_dict() if result.raw_text else None,
            "usage": result.usage.to_dict() if result.usage else None,
            "input": job.input,
            "duration_ms": duration_ms,
        }
        return {"execution_id": job.execution_id, "status": status.value, "duration_ms": duration_ms}

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("Job %s failed: %s", job.execution_id, exc, exc_info=True)

        await gw._execution_repo.update_status(
            job.execution_id, ExecutionStatus.FAILED, error=str(exc)
        )

        notify_args = {
            "execution_id": job.execution_id,
            "agent_id": agent.id,
            "status": "failed",
            "message": job.message,
            "config": agent.notifications,
            "error": str(exc),
            "input": job.input,
            "duration_ms": duration_ms,
        }
        return {"execution_id": job.execution_id, "status": "failed", "duration_ms": duration_ms}

    finally:
        gw._execution_handles.pop(job.execution_id, None)

        # Fire webhook / other notifications after releasing the handle
        if notify_args is not None:
            await _fire_notifications_async(gw, notify_args)


async def _fire_notifications_async(gw: Any, notify_args: dict[str, Any]) -> None:
    """Fire notifications directly via the notification engine (async).

    ``gw.fire_notifications()`` uses ``asyncio.create_task()``, which
    requires a running event loop but doesn't await the result.  Since we
    ARE in the event loop here, we call the notification engine directly so
    we can await delivery and catch any errors.
    """
    from agent_gateway.notifications.models import (
        AgentNotificationConfig,
        build_notification_event,
    )

    config = notify_args.get("config")
    if not config or not gw._notification_engine.has_backends:
        return

    if not isinstance(config, AgentNotificationConfig):
        return

    event = build_notification_event(
        execution_id=notify_args["execution_id"],
        agent_id=notify_args["agent_id"],
        status=notify_args["status"],
        message=notify_args["message"],
        result=notify_args.get("result"),
        error=notify_args.get("error"),
        usage=notify_args.get("usage"),
        duration_ms=notify_args.get("duration_ms", 0),
        input=notify_args.get("input"),
    )

    try:
        await gw._notification_engine.notify(event, config)
        logger.info(
            "Notifications fired: status=%s execution_id=%s",
            notify_args["status"],
            notify_args["execution_id"],
        )
    except Exception:
        logger.warning(
            "Failed to fire notifications for execution %s",
            notify_args["execution_id"],
            exc_info=True,
        )
