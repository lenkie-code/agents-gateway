"""Tests for session rehydration from persistence."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

from agent_gateway.chat.session import ChatSession, SessionStore
from agent_gateway.persistence.domain import ConversationMessage, ConversationRecord
from agent_gateway.persistence.null import NullConversationRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conv_record(
    conversation_id: str = "sess_abc",
    agent_id: str = "test-agent",
    user_id: str | None = "user1",
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    message_count: int = 4,
) -> ConversationRecord:
    now = datetime.now(UTC)
    return ConversationRecord(
        conversation_id=conversation_id,
        agent_id=agent_id,
        user_id=user_id,
        message_count=message_count,
        created_at=created_at or now,
        updated_at=updated_at or now,
    )


def _make_conv_messages(
    conversation_id: str = "sess_abc",
    pairs: int = 2,
) -> list[ConversationMessage]:
    msgs: list[ConversationMessage] = []
    for i in range(pairs):
        msgs.append(
            ConversationMessage(
                message_id=f"msg-u{i}",
                conversation_id=conversation_id,
                role="user",
                content=f"Hello {i}",
                created_at=datetime.now(UTC),
            )
        )
        msgs.append(
            ConversationMessage(
                message_id=f"msg-a{i}",
                conversation_id=conversation_id,
                role="assistant",
                content=f"Hi {i}",
                created_at=datetime.now(UTC),
            )
        )
    return msgs


class _FakeGateway:
    """Minimal stand-in for Gateway with the fields _get_or_restore_session needs."""

    def __init__(
        self,
        session_store: SessionStore | None = None,
        conversation_repo: Any = None,
    ) -> None:
        self._session_store = session_store or SessionStore()
        self._conversation_repo = conversation_repo or NullConversationRepository()
        self._rehydration_tasks: dict[str, Any] = {}

    # Bind the real methods from Gateway
    from agent_gateway.gateway import Gateway

    _get_or_restore_session = Gateway._get_or_restore_session
    _rehydrate_session = Gateway._rehydrate_session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_rehydration_from_persistence() -> None:
    """Rehydration loads conversation + messages from DB into session cache."""
    repo = AsyncMock()
    record = _make_conv_record()
    repo.get = AsyncMock(return_value=record)
    repo.get_messages = AsyncMock(return_value=_make_conv_messages())

    store = SessionStore()
    gw = _FakeGateway(session_store=store, conversation_repo=repo)

    session = await gw._get_or_restore_session("sess_abc")
    assert session is not None
    assert session.session_id == "sess_abc"
    assert session.agent_id == "test-agent"
    assert session.user_id == "user1"
    assert len(session.messages) == 4  # 2 user + 2 assistant
    assert session.messages[0]["role"] == "user"
    assert session.messages[1]["role"] == "assistant"

    # Should now be in the cache
    cached = store.get_session("sess_abc")
    assert cached is session


async def test_cache_hit_no_db_call() -> None:
    """When session is in cache, DB is not queried."""
    repo = AsyncMock()
    store = SessionStore()
    existing = store.create_session("test-agent")

    gw = _FakeGateway(session_store=store, conversation_repo=repo)
    session = await gw._get_or_restore_session(existing.session_id)

    assert session is existing
    repo.get.assert_not_called()


async def test_returns_none_when_not_in_db() -> None:
    """Unknown session_id returns None without error."""
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)

    gw = _FakeGateway(conversation_repo=repo)
    session = await gw._get_or_restore_session("nonexistent")
    assert session is None


async def test_null_repo_returns_none() -> None:
    """NullConversationRepository gracefully returns None."""
    gw = _FakeGateway(conversation_repo=NullConversationRepository())
    session = await gw._get_or_restore_session("sess_xyz")
    assert session is None


async def test_rehydrated_session_ttl() -> None:
    """_last_active is set based on updated_at, not current time."""
    age = 120.0  # 2 minutes old
    updated = datetime.now(UTC) - timedelta(seconds=age)
    record = _make_conv_record(updated_at=updated)

    repo = AsyncMock()
    repo.get = AsyncMock(return_value=record)
    repo.get_messages = AsyncMock(return_value=_make_conv_messages(pairs=1))

    store = SessionStore(ttl_seconds=600)
    record.message_count = 2
    gw = _FakeGateway(session_store=store, conversation_repo=repo)

    session = await gw._get_or_restore_session("sess_abc")
    assert session is not None

    # _last_active should be ~120s in the past relative to monotonic clock
    elapsed = time.monotonic() - session._last_active
    assert elapsed >= age - 2  # allow small timing tolerance


async def test_expired_session_not_rehydrated() -> None:
    """Session older than TTL is not rehydrated."""
    ttl = 300  # 5 minutes
    updated = datetime.now(UTC) - timedelta(seconds=ttl + 60)  # expired
    record = _make_conv_record(updated_at=updated)

    repo = AsyncMock()
    repo.get = AsyncMock(return_value=record)

    store = SessionStore(ttl_seconds=ttl)
    gw = _FakeGateway(session_store=store, conversation_repo=repo)

    session = await gw._get_or_restore_session("sess_abc")
    assert session is None
    repo.get_messages.assert_not_called()


async def test_dangling_user_message_dropped() -> None:
    """If last DB message is role=user, it's dropped."""
    msgs = _make_conv_messages(pairs=1)
    # Add a dangling user message
    msgs.append(
        ConversationMessage(
            message_id="msg-dangling",
            conversation_id="sess_abc",
            role="user",
            content="unanswered",
            created_at=datetime.now(UTC),
        )
    )

    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_make_conv_record(message_count=3))
    repo.get_messages = AsyncMock(return_value=msgs)

    gw = _FakeGateway()
    gw._conversation_repo = repo

    session = await gw._get_or_restore_session("sess_abc")
    assert session is not None
    # Should have 2 messages (1 pair), dangling user dropped
    assert len(session.messages) == 2
    assert session.messages[-1]["role"] == "assistant"


async def test_lru_eviction_during_restore() -> None:
    """Fill store to max, restore triggers eviction of oldest."""
    store = SessionStore(max_sessions=2)
    s1 = store.create_session("agent-a")
    s2 = store.create_session("agent-b")
    assert store.session_count == 2

    # Restore a third session — should evict s1 (oldest)
    session = ChatSession(
        session_id="sess_restored",
        agent_id="agent-c",
        messages=[],
    )
    store.restore_session(session)

    assert store.session_count == 2
    assert store.get_session(s1.session_id) is None
    assert store.get_session(s2.session_id) is not None
    assert store.get_session("sess_restored") is session
