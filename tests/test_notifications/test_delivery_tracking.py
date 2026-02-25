"""Tests for notification delivery tracking."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_gateway.notifications.models import sanitize_target
from agent_gateway.persistence.domain import NotificationDeliveryRecord
from agent_gateway.persistence.null import NullNotificationRepository


class TestSanitizeTarget:
    """Tests for the sanitize_target helper."""

    def test_strips_query_params_from_url(self) -> None:
        url = "https://hooks.example.com/webhook?token=secret&key=123"
        assert sanitize_target(url) == "https://hooks.example.com/webhook"

    def test_strips_fragment_from_url(self) -> None:
        url = "https://hooks.example.com/webhook#section"
        assert sanitize_target(url) == "https://hooks.example.com/webhook"

    def test_preserves_path(self) -> None:
        url = "https://hooks.example.com/a/b/c"
        assert sanitize_target(url) == "https://hooks.example.com/a/b/c"

    def test_non_url_unchanged(self) -> None:
        assert sanitize_target("#general") == "#general"
        assert sanitize_target("my-webhook") == "my-webhook"

    def test_empty_string(self) -> None:
        assert sanitize_target("") == ""

    def test_http_url(self) -> None:
        url = "http://localhost:8080/hook?key=val"
        assert sanitize_target(url) == "http://localhost:8080/hook"


class TestNotificationDeliveryRecord:
    """Tests for the domain model."""

    def test_defaults(self) -> None:
        record = NotificationDeliveryRecord()
        assert record.id is None
        assert record.status == "pending"
        assert record.attempts == 0
        assert record.last_error is None

    def test_custom_values(self) -> None:
        now = datetime.now(UTC)
        record = NotificationDeliveryRecord(
            id=1,
            execution_id="exec-1",
            agent_id="agent-1",
            event_type="execution.completed",
            channel="slack",
            target="#general",
            status="delivered",
            attempts=1,
            created_at=now,
            delivered_at=now,
        )
        assert record.id == 1
        assert record.channel == "slack"
        assert record.status == "delivered"


class TestNullNotificationRepository:
    """Tests for the null repo pattern."""

    @pytest.fixture
    def repo(self) -> NullNotificationRepository:
        return NullNotificationRepository()

    async def test_create_noop(self, repo: NullNotificationRepository) -> None:
        record = NotificationDeliveryRecord(execution_id="x", agent_id="a")
        await repo.create(record)  # Should not raise

    async def test_list_recent_empty(self, repo: NullNotificationRepository) -> None:
        result = await repo.list_recent()
        assert result == []

    async def test_count_zero(self, repo: NullNotificationRepository) -> None:
        result = await repo.count()
        assert result == 0

    async def test_get_none(self, repo: NullNotificationRepository) -> None:
        result = await repo.get(1)
        assert result is None

    async def test_list_recent_with_filters(self, repo: NullNotificationRepository) -> None:
        result = await repo.list_recent(
            status="failed", agent_id="x", channel="slack", execution_id="e"
        )
        assert result == []

    async def test_count_with_filters(self, repo: NullNotificationRepository) -> None:
        result = await repo.count(status="delivered", agent_id="a")
        assert result == 0

    async def test_update_status_noop(self, repo: NullNotificationRepository) -> None:
        await repo.update_status(1, status="delivered", attempts=1)  # Should not raise
