"""Tests for SQL-backed memory backend with per-user scoping."""

from __future__ import annotations

import pytest

from agent_gateway.memory.backends.sql import SqlMemoryBackend, SqlMemoryRepository
from agent_gateway.memory.domain import MemoryRecord, MemoryType
from agent_gateway.persistence.backends.sqlite import SqliteBackend


@pytest.fixture
async def backend(tmp_path) -> SqliteBackend:
    db_path = tmp_path / "test.db"
    b = SqliteBackend(path=str(db_path))
    await b.initialize()
    yield b
    await b.dispose()


@pytest.fixture
def sql_memory(backend: SqliteBackend) -> SqlMemoryBackend:
    return SqlMemoryBackend(backend._session_factory)


@pytest.fixture
def repo(sql_memory: SqlMemoryBackend) -> SqlMemoryRepository:
    return sql_memory.memory_repo


def _make_record(
    memory_id: str = "m1",
    agent_id: str = "agent-1",
    content: str = "test fact",
    user_id: str | None = None,
    memory_type: MemoryType = MemoryType.SEMANTIC,
    importance: float = 0.5,
) -> MemoryRecord:
    return MemoryRecord(
        id=memory_id,
        agent_id=agent_id,
        content=content,
        user_id=user_id,
        memory_type=memory_type,
        importance=importance,
    )


class TestSqlMemoryCRUD:
    async def test_save_and_get(self, repo: SqlMemoryRepository) -> None:
        record = _make_record()
        await repo.save(record)
        fetched = await repo.get("agent-1", "m1")
        assert fetched is not None
        assert fetched.content == "test fact"

    async def test_get_wrong_agent(self, repo: SqlMemoryRepository) -> None:
        await repo.save(_make_record())
        assert await repo.get("wrong-agent", "m1") is None

    async def test_upsert_updates_existing(self, repo: SqlMemoryRepository) -> None:
        await repo.save(_make_record(content="original"))
        await repo.save(_make_record(content="updated"))
        fetched = await repo.get("agent-1", "m1")
        assert fetched is not None
        assert fetched.content == "updated"

    async def test_delete(self, repo: SqlMemoryRepository) -> None:
        await repo.save(_make_record())
        assert await repo.delete("agent-1", "m1") is True
        assert await repo.get("agent-1", "m1") is None

    async def test_delete_wrong_agent(self, repo: SqlMemoryRepository) -> None:
        await repo.save(_make_record())
        assert await repo.delete("wrong-agent", "m1") is False

    async def test_delete_nonexistent(self, repo: SqlMemoryRepository) -> None:
        assert await repo.delete("agent-1", "nope") is False


class TestSqlMemoryUserScoping:
    async def test_global_memory_has_null_user_id(self, repo: SqlMemoryRepository) -> None:
        await repo.save(_make_record(user_id=None))
        records = await repo.list_memories("agent-1", user_id=None)
        assert len(records) == 1
        assert records[0].user_id is None

    async def test_user_memory_isolated(self, repo: SqlMemoryRepository) -> None:
        await repo.save(_make_record(memory_id="g1", user_id=None, content="global"))
        await repo.save(_make_record(memory_id="u1", user_id="user-a", content="user-a fact"))
        await repo.save(_make_record(memory_id="u2", user_id="user-b", content="user-b fact"))

        # User A should only see their own + global
        user_a = await repo.list_memories("agent-1", user_id="user-a", include_global=True)
        assert len(user_a) == 2
        contents = {r.content for r in user_a}
        assert "global" in contents
        assert "user-a fact" in contents
        assert "user-b fact" not in contents

    async def test_user_only_excludes_global(self, repo: SqlMemoryRepository) -> None:
        await repo.save(_make_record(memory_id="g1", user_id=None, content="global"))
        await repo.save(_make_record(memory_id="u1", user_id="user-a", content="user-a fact"))

        results = await repo.list_memories("agent-1", user_id="user-a", include_global=False)
        assert len(results) == 1
        assert results[0].content == "user-a fact"

    async def test_global_only_when_no_user(self, repo: SqlMemoryRepository) -> None:
        await repo.save(_make_record(memory_id="g1", user_id=None))
        await repo.save(_make_record(memory_id="u1", user_id="user-a"))

        results = await repo.list_memories("agent-1", user_id=None)
        assert len(results) == 1
        assert results[0].user_id is None


class TestSqlMemorySearch:
    async def test_search_finds_matching(self, repo: SqlMemoryRepository) -> None:
        await repo.save(_make_record(memory_id="m1", content="user prefers dark mode"))
        await repo.save(_make_record(memory_id="m2", content="user likes python"))

        results = await repo.search("agent-1", "dark mode")
        assert len(results) >= 1
        assert results[0].record.content == "user prefers dark mode"

    async def test_search_respects_user_scope(self, repo: SqlMemoryRepository) -> None:
        await repo.save(_make_record(memory_id="g1", user_id=None, content="global dark mode"))
        await repo.save(_make_record(memory_id="u1", user_id="user-a", content="user dark mode"))

        # Search as user-a — should find both
        results = await repo.search("agent-1", "dark mode", user_id="user-a", include_global=True)
        assert len(results) == 2

        # User-only — should find just the user memory
        results = await repo.search("agent-1", "dark mode", user_id="user-a", include_global=False)
        assert len(results) == 1
        assert results[0].record.user_id == "user-a"

    async def test_search_boosts_user_memories(self, repo: SqlMemoryRepository) -> None:
        await repo.save(_make_record(memory_id="g1", user_id=None, content="dark mode setting"))
        await repo.save(
            _make_record(memory_id="u1", user_id="user-a", content="dark mode setting")
        )

        results = await repo.search("agent-1", "dark mode", user_id="user-a", include_global=True)
        assert len(results) == 2
        # User memory should be ranked first (boosted)
        assert results[0].record.user_id == "user-a"

    async def test_search_empty_query_words(self, repo: SqlMemoryRepository) -> None:
        await repo.save(_make_record())
        results = await repo.search("agent-1", "")
        assert results == []

    async def test_search_by_memory_type(self, repo: SqlMemoryRepository) -> None:
        await repo.save(
            _make_record(memory_id="s1", content="fact", memory_type=MemoryType.SEMANTIC)
        )
        await repo.save(
            _make_record(memory_id="e1", content="event fact", memory_type=MemoryType.EPISODIC)
        )

        results = await repo.search("agent-1", "fact", memory_type=MemoryType.SEMANTIC)
        assert len(results) == 1
        assert results[0].record.memory_type == MemoryType.SEMANTIC


class TestSqlMemoryBulkOps:
    async def test_delete_all_no_filter(self, repo: SqlMemoryRepository) -> None:
        """delete_all with user_id=None removes ALL memories for the agent."""
        for i in range(5):
            await repo.save(_make_record(memory_id=f"m{i}", user_id=None))
        await repo.save(_make_record(memory_id="u1", user_id="user-a"))

        deleted = await repo.delete_all("agent-1", user_id=None)
        assert deleted == 6

    async def test_delete_all_user(self, repo: SqlMemoryRepository) -> None:
        await repo.save(_make_record(memory_id="g1", user_id=None))
        for i in range(3):
            await repo.save(_make_record(memory_id=f"u{i}", user_id="user-a"))

        deleted = await repo.delete_all("agent-1", user_id="user-a")
        assert deleted == 3
        assert await repo.get("agent-1", "g1") is not None

    async def test_count_all(self, repo: SqlMemoryRepository) -> None:
        """count with user_id=None returns total count for the agent."""
        for i in range(4):
            await repo.save(_make_record(memory_id=f"m{i}", user_id=None))
        await repo.save(_make_record(memory_id="u1", user_id="user-a"))

        assert await repo.count("agent-1", user_id=None) == 5

    async def test_count_user(self, repo: SqlMemoryRepository) -> None:
        await repo.save(_make_record(memory_id="g1", user_id=None))
        for i in range(3):
            await repo.save(_make_record(memory_id=f"u{i}", user_id="user-a"))

        assert await repo.count("agent-1", user_id="user-a") == 3


class TestSqlMemoryBackend:
    async def test_initialize_dispose(self, sql_memory: SqlMemoryBackend) -> None:
        await sql_memory.initialize()
        await sql_memory.dispose()

    def test_memory_repo_property(self, sql_memory: SqlMemoryBackend) -> None:
        assert isinstance(sql_memory.memory_repo, SqlMemoryRepository)
