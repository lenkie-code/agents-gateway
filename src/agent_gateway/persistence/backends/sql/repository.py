"""CRUD operations for SQL persistence backends (SQLite, PostgreSQL)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_gateway.persistence.domain import (
    AuditLogEntry,
    ExecutionRecord,
    ExecutionStep,
    ScheduleRecord,
)


class ExecutionRepository:
    """CRUD operations for execution records and steps."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(self, execution: ExecutionRecord) -> None:
        """Insert a new execution record."""
        async with self._session_factory() as session:
            session.add(execution)
            await session.commit()

    async def get(self, execution_id: str) -> ExecutionRecord | None:
        """Fetch an execution by ID."""
        async with self._session_factory() as session:
            return await session.get(ExecutionRecord, execution_id)

    async def update_status(
        self,
        execution_id: str,
        status: str,
        **fields: Any,
    ) -> None:
        """Update the status and optional fields of an execution."""
        async with self._session_factory() as session:
            record = await session.get(ExecutionRecord, execution_id)
            if record is None:
                return
            record.status = status
            for key, value in fields.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            await session.commit()

    async def update_result(
        self,
        execution_id: str,
        result: dict[str, Any],
        usage: dict[str, Any],
    ) -> None:
        """Update the result and usage of a completed execution."""
        async with self._session_factory() as session:
            record = await session.get(ExecutionRecord, execution_id)
            if record is None:
                return
            record.result = result
            record.usage = usage
            record.completed_at = datetime.now(UTC)
            await session.commit()

    async def list_by_agent(
        self,
        agent_id: str,
        limit: int = 50,
    ) -> list[ExecutionRecord]:
        """List executions for an agent, most recent first."""
        async with self._session_factory() as session:
            stmt = (
                select(ExecutionRecord)
                .where(ExecutionRecord.agent_id == agent_id)  # type: ignore[arg-type]
                .order_by(ExecutionRecord.created_at.desc())  # type: ignore[union-attr]
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def add_step(self, step: ExecutionStep) -> None:
        """Insert a new execution step."""
        async with self._session_factory() as session:
            session.add(step)
            await session.commit()

    async def get_with_steps(self, execution_id: str) -> ExecutionRecord | None:
        """Fetch an execution by ID with all its steps eagerly loaded."""
        async with self._session_factory() as session:
            record = await session.get(ExecutionRecord, execution_id)
            if record is None:
                return None
            # Load steps separately (imperative mapping without relationships)
            stmt = (
                select(ExecutionStep)
                .where(ExecutionStep.execution_id == execution_id)  # type: ignore[arg-type]
                .order_by(ExecutionStep.sequence)  # type: ignore[arg-type]
            )
            result = await session.execute(stmt)
            record.steps = list(result.scalars().all())
            return record

    async def list_all(
        self,
        limit: int = 50,
        offset: int = 0,
        agent_id: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
    ) -> list[ExecutionRecord]:
        """List executions across all agents, most recent first."""
        async with self._session_factory() as session:
            stmt = select(ExecutionRecord).order_by(
                ExecutionRecord.created_at.desc()  # type: ignore[union-attr]
            )
            if agent_id is not None:
                stmt = stmt.where(
                    ExecutionRecord.agent_id == agent_id  # type: ignore[arg-type]
                )
            if status is not None:
                stmt = stmt.where(
                    ExecutionRecord.status == status  # type: ignore[arg-type]
                )
            if since is not None:
                stmt = stmt.where(
                    ExecutionRecord.created_at >= since  # type: ignore[operator,arg-type]
                )
            stmt = stmt.limit(limit).offset(offset)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_all(
        self,
        agent_id: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
    ) -> int:
        """Count executions with optional filters."""
        async with self._session_factory() as session:
            stmt = select(func.count()).select_from(ExecutionRecord)
            if agent_id is not None:
                stmt = stmt.where(
                    ExecutionRecord.agent_id == agent_id  # type: ignore[arg-type]
                )
            if status is not None:
                stmt = stmt.where(
                    ExecutionRecord.status == status  # type: ignore[arg-type]
                )
            if since is not None:
                stmt = stmt.where(
                    ExecutionRecord.created_at >= since  # type: ignore[operator,arg-type]
                )
            result = await session.execute(stmt)
            return result.scalar_one()

    async def cost_by_day(self, days: int = 30) -> list[dict[str, Any]]:
        """Daily cost aggregation for the last N days."""
        since = datetime.now(UTC) - timedelta(days=days)
        async with self._session_factory() as session:
            # Use SQLite-compatible date extraction; works on Postgres too
            stmt = text(
                """
                SELECT
                    date(created_at) as day,
                    COUNT(*) as execution_count,
                    SUM(CAST(json_extract(usage, '$.cost_usd') AS REAL)) as total_cost_usd,
                    SUM(CAST(json_extract(usage, '$.input_tokens') AS INTEGER)) as total_input_tokens,
                    SUM(CAST(json_extract(usage, '$.output_tokens') AS INTEGER)) as total_output_tokens
                FROM executions
                WHERE created_at >= :since
                  AND usage IS NOT NULL
                GROUP BY date(created_at)
                ORDER BY day ASC
                """
            )
            result = await session.execute(stmt, {"since": since.isoformat()})
            return [dict(row._mapping) for row in result]

    async def cost_by_agent(self, days: int = 30) -> list[dict[str, Any]]:
        """Per-agent cost aggregation for the last N days."""
        since = datetime.now(UTC) - timedelta(days=days)
        async with self._session_factory() as session:
            stmt = text(
                """
                SELECT
                    agent_id,
                    COUNT(*) as execution_count,
                    SUM(CAST(json_extract(usage, '$.cost_usd') AS REAL)) as total_cost_usd,
                    SUM(CAST(json_extract(usage, '$.input_tokens') AS INTEGER)) as total_input_tokens,
                    SUM(CAST(json_extract(usage, '$.output_tokens') AS INTEGER)) as total_output_tokens
                FROM executions
                WHERE created_at >= :since
                  AND usage IS NOT NULL
                GROUP BY agent_id
                ORDER BY total_cost_usd DESC
                """
            )
            result = await session.execute(stmt, {"since": since.isoformat()})
            return [dict(row._mapping) for row in result]

    async def executions_by_day(self, days: int = 30) -> list[dict[str, Any]]:
        """Daily execution count by status for the last N days."""
        since = datetime.now(UTC) - timedelta(days=days)
        async with self._session_factory() as session:
            stmt = text(
                """
                SELECT
                    date(created_at) as day,
                    COUNT(*) as count,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count
                FROM executions
                WHERE created_at >= :since
                GROUP BY date(created_at)
                ORDER BY day ASC
                """
            )
            result = await session.execute(stmt, {"since": since.isoformat()})
            return [dict(row._mapping) for row in result]


class ScheduleRepository:
    """CRUD operations for schedule records."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def upsert(self, record: ScheduleRecord) -> None:
        """Insert or update a schedule record."""
        async with self._session_factory() as session:
            existing = await session.get(ScheduleRecord, record.id)
            if existing is None:
                session.add(record)
            else:
                existing.agent_id = record.agent_id
                existing.name = record.name
                existing.cron_expr = record.cron_expr
                existing.message = record.message
                existing.input = record.input
                existing.enabled = record.enabled
                existing.timezone = record.timezone
                existing.next_run_at = record.next_run_at
                existing.deleted_at = None  # un-delete if re-added
            await session.commit()

    async def upsert_batch(self, records: list[ScheduleRecord]) -> None:
        """Upsert multiple schedule records in a single transaction."""
        if not records:
            return
        async with self._session_factory() as session:
            for record in records:
                existing = await session.get(ScheduleRecord, record.id)
                if existing is None:
                    session.add(record)
                else:
                    existing.name = record.name
                    existing.cron_expr = record.cron_expr
                    existing.message = record.message
                    existing.input = record.input
                    existing.enabled = record.enabled
                    existing.timezone = record.timezone
                    existing.next_run_at = record.next_run_at
                    existing.deleted_at = None
            await session.commit()

    async def get(self, schedule_id: str) -> ScheduleRecord | None:
        """Fetch a schedule by ID."""
        async with self._session_factory() as session:
            return await session.get(ScheduleRecord, schedule_id)

    async def list_all(self, agent_id: str | None = None) -> list[ScheduleRecord]:
        """List all non-deleted schedules, optionally filtered by agent."""
        async with self._session_factory() as session:
            stmt = select(ScheduleRecord).where(
                ScheduleRecord.deleted_at.is_(None)  # type: ignore[union-attr]
            )
            if agent_id is not None:
                stmt = stmt.where(
                    ScheduleRecord.agent_id == agent_id  # type: ignore[arg-type]
                )
            stmt = stmt.order_by(ScheduleRecord.created_at)  # type: ignore[arg-type]
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update_last_run(
        self,
        schedule_id: str,
        last_run_at: datetime,
        next_run_at: datetime | None,
    ) -> None:
        """Update the last and next run times for a schedule."""
        async with self._session_factory() as session:
            record = await session.get(ScheduleRecord, schedule_id)
            if record is None:
                return
            record.last_run_at = last_run_at
            record.next_run_at = next_run_at
            await session.commit()

    async def update_next_run(
        self,
        schedule_id: str,
        next_run_at: datetime | None,
    ) -> None:
        """Update only the next run time for a schedule."""
        async with self._session_factory() as session:
            record = await session.get(ScheduleRecord, schedule_id)
            if record is None:
                return
            record.next_run_at = next_run_at
            await session.commit()

    async def update_enabled(self, schedule_id: str, enabled: bool) -> None:
        """Update the enabled state of a schedule."""
        async with self._session_factory() as session:
            record = await session.get(ScheduleRecord, schedule_id)
            if record is None:
                return
            record.enabled = enabled
            await session.commit()


class AuditRepository:
    """CRUD operations for audit log entries."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def log(
        self,
        event_type: str,
        actor: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Write an audit log entry."""
        entry = AuditLogEntry(
            event_type=event_type,
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
            ip_address=ip_address,
        )
        async with self._session_factory() as session:
            session.add(entry)
            await session.commit()

    async def list_recent(self, limit: int = 100) -> list[AuditLogEntry]:
        """List recent audit log entries, most recent first."""
        async with self._session_factory() as session:
            stmt = (
                select(AuditLogEntry)
                .order_by(AuditLogEntry.created_at.desc())  # type: ignore[union-attr]
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
