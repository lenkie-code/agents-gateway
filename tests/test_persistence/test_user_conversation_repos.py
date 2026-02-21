"""Tests for UserRepository and ConversationRepository (SQL + Null)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_gateway.persistence.backends.sqlite import SqliteBackend
from agent_gateway.persistence.domain import (
    ConversationMessage,
    ConversationRecord,
    UserProfile,
)
from agent_gateway.persistence.null import NullConversationRepository, NullUserRepository

# --- Null repository tests ---


class TestNullUserRepository:
    async def test_upsert_is_noop(self) -> None:
        repo = NullUserRepository()
        await repo.upsert(UserProfile(user_id="u1"))

    async def test_get_returns_none(self) -> None:
        repo = NullUserRepository()
        assert await repo.get("u1") is None

    async def test_delete_returns_false(self) -> None:
        repo = NullUserRepository()
        assert await repo.delete("u1") is False


class TestNullConversationRepository:
    async def test_create_is_noop(self) -> None:
        repo = NullConversationRepository()
        await repo.create(ConversationRecord(conversation_id="c1", agent_id="a1"))

    async def test_get_returns_none(self) -> None:
        repo = NullConversationRepository()
        assert await repo.get("c1") is None

    async def test_list_by_user_returns_empty(self) -> None:
        repo = NullConversationRepository()
        assert await repo.list_by_user("u1") == []

    async def test_get_messages_returns_empty(self) -> None:
        repo = NullConversationRepository()
        assert await repo.get_messages("c1") == []

    async def test_delete_returns_false(self) -> None:
        repo = NullConversationRepository()
        assert await repo.delete("c1") is False


# --- SQL repository tests ---


@pytest.fixture
async def backend(tmp_path) -> SqliteBackend:
    db_path = tmp_path / "test.db"
    b = SqliteBackend(path=str(db_path))
    await b.initialize()
    yield b
    await b.dispose()


class TestSqlUserRepository:
    async def test_upsert_create(self, backend: SqliteBackend) -> None:
        repo = backend.user_repo
        now = datetime.now(UTC)
        profile = UserProfile(
            user_id="u1",
            display_name="Alice",
            email="alice@example.com",
            first_seen_at=now,
            last_seen_at=now,
        )
        await repo.upsert(profile)
        fetched = await repo.get("u1")
        assert fetched is not None
        assert fetched.display_name == "Alice"
        assert fetched.email == "alice@example.com"

    async def test_upsert_update(self, backend: SqliteBackend) -> None:
        repo = backend.user_repo
        now = datetime.now(UTC)
        await repo.upsert(
            UserProfile(user_id="u1", display_name="Alice", first_seen_at=now, last_seen_at=now)
        )
        await repo.upsert(
            UserProfile(user_id="u1", display_name="Alice Updated", last_seen_at=now)
        )
        fetched = await repo.get("u1")
        assert fetched is not None
        assert fetched.display_name == "Alice Updated"

    async def test_get_nonexistent(self, backend: SqliteBackend) -> None:
        repo = backend.user_repo
        assert await repo.get("nonexistent") is None

    async def test_delete(self, backend: SqliteBackend) -> None:
        repo = backend.user_repo
        now = datetime.now(UTC)
        await repo.upsert(
            UserProfile(user_id="u1", display_name="Alice", first_seen_at=now, last_seen_at=now)
        )
        assert await repo.delete("u1") is True
        assert await repo.get("u1") is None

    async def test_delete_nonexistent(self, backend: SqliteBackend) -> None:
        repo = backend.user_repo
        assert await repo.delete("nope") is False


class TestSqlConversationRepository:
    async def test_create_and_get(self, backend: SqliteBackend) -> None:
        repo = backend.conversation_repo
        now = datetime.now(UTC)
        record = ConversationRecord(
            conversation_id="c1",
            agent_id="agent-1",
            user_id="u1",
            title="Test Chat",
            created_at=now,
            updated_at=now,
        )
        await repo.create(record)
        fetched = await repo.get("c1")
        assert fetched is not None
        assert fetched.title == "Test Chat"
        assert fetched.agent_id == "agent-1"

    async def test_list_by_user(self, backend: SqliteBackend) -> None:
        repo = backend.conversation_repo
        now = datetime.now(UTC)
        for i in range(3):
            await repo.create(
                ConversationRecord(
                    conversation_id=f"c{i}",
                    agent_id="agent-1",
                    user_id="u1",
                    created_at=now,
                    updated_at=now,
                )
            )
        # Different user
        await repo.create(
            ConversationRecord(
                conversation_id="c99",
                agent_id="agent-1",
                user_id="u2",
                created_at=now,
                updated_at=now,
            )
        )

        results = await repo.list_by_user("u1")
        assert len(results) == 3
        assert all(r.user_id == "u1" for r in results)

    async def test_list_by_user_with_agent_filter(self, backend: SqliteBackend) -> None:
        repo = backend.conversation_repo
        now = datetime.now(UTC)
        await repo.create(
            ConversationRecord(
                conversation_id="c1",
                agent_id="agent-1",
                user_id="u1",
                created_at=now,
                updated_at=now,
            )
        )
        await repo.create(
            ConversationRecord(
                conversation_id="c2",
                agent_id="agent-2",
                user_id="u1",
                created_at=now,
                updated_at=now,
            )
        )
        results = await repo.list_by_user("u1", agent_id="agent-1")
        assert len(results) == 1
        assert results[0].agent_id == "agent-1"

    async def test_add_and_get_messages(self, backend: SqliteBackend) -> None:
        repo = backend.conversation_repo
        now = datetime.now(UTC)
        await repo.create(
            ConversationRecord(
                conversation_id="c1",
                agent_id="agent-1",
                user_id="u1",
                created_at=now,
                updated_at=now,
            )
        )
        await repo.add_message(
            ConversationMessage(
                message_id="m1",
                conversation_id="c1",
                role="user",
                content="Hello",
                created_at=now,
            )
        )
        await repo.add_message(
            ConversationMessage(
                message_id="m2",
                conversation_id="c1",
                role="assistant",
                content="Hi there!",
                created_at=now,
            )
        )

        messages = await repo.get_messages("c1")
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

    async def test_update_summary(self, backend: SqliteBackend) -> None:
        repo = backend.conversation_repo
        now = datetime.now(UTC)
        await repo.create(
            ConversationRecord(
                conversation_id="c1",
                agent_id="agent-1",
                user_id="u1",
                created_at=now,
                updated_at=now,
            )
        )
        await repo.update_summary("c1", "User discussed travel plans to Paris")
        fetched = await repo.get("c1")
        assert fetched is not None
        assert fetched.summary == "User discussed travel plans to Paris"

    async def test_update(self, backend: SqliteBackend) -> None:
        repo = backend.conversation_repo
        now = datetime.now(UTC)
        record = ConversationRecord(
            conversation_id="c1",
            agent_id="agent-1",
            user_id="u1",
            message_count=0,
            created_at=now,
            updated_at=now,
        )
        await repo.create(record)
        record.message_count = 5
        record.title = "Updated Title"
        await repo.update(record)

        fetched = await repo.get("c1")
        assert fetched is not None
        assert fetched.message_count == 5
        assert fetched.title == "Updated Title"

    async def test_delete(self, backend: SqliteBackend) -> None:
        repo = backend.conversation_repo
        now = datetime.now(UTC)
        await repo.create(
            ConversationRecord(
                conversation_id="c1",
                agent_id="agent-1",
                user_id="u1",
                created_at=now,
                updated_at=now,
            )
        )
        assert await repo.delete("c1") is True
        assert await repo.get("c1") is None

    async def test_delete_nonexistent(self, backend: SqliteBackend) -> None:
        repo = backend.conversation_repo
        assert await repo.delete("nope") is False
