"""Tests for per-user memory scoping, layered context, and compaction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent_gateway.config import CompactionConfig, MemoryConfig
from agent_gateway.memory.backends.file import FileMemoryBackend
from agent_gateway.memory.domain import MemoryRecord, MemorySource
from agent_gateway.memory.manager import MemoryManager


@dataclass
class FakeLLMResponse:
    text: str


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "agents" / "test-agent").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def llm_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def memory_config() -> MemoryConfig:
    return MemoryConfig(enabled=True)


@pytest.fixture
async def manager(
    workspace: Path, llm_client: AsyncMock, memory_config: MemoryConfig
) -> MemoryManager:
    backend = FileMemoryBackend(workspace)
    await backend.initialize()
    return MemoryManager(backend=backend, llm_client=llm_client, config=memory_config)


class TestFileBackendUserScoping:
    """File backend stores per-user memories in separate files."""

    async def test_user_memory_isolated_from_global(self, manager: MemoryManager) -> None:
        await manager.save(MemoryRecord(id="a", agent_id="test-agent", content="global fact"))
        await manager.save(
            MemoryRecord(id="b", agent_id="test-agent", content="user pref", user_id="user1")
        )
        # User-only query should return only user memories
        results = await manager.repo.list_memories(
            "test-agent", user_id="user1", include_global=False
        )
        assert len(results) == 1
        assert results[0].content == "user pref"

    async def test_list_with_global_includes_both(self, manager: MemoryManager) -> None:
        await manager.save(MemoryRecord(id="a", agent_id="test-agent", content="global fact"))
        await manager.save(
            MemoryRecord(id="b", agent_id="test-agent", content="user pref", user_id="user1")
        )
        results = await manager.repo.list_memories(
            "test-agent", user_id="user1", include_global=True
        )
        assert len(results) == 2

    async def test_search_user_only(self, manager: MemoryManager) -> None:
        await manager.save(MemoryRecord(id="a", agent_id="test-agent", content="global fact"))
        await manager.save(
            MemoryRecord(id="b", agent_id="test-agent", content="user fact", user_id="user1")
        )
        results = await manager.repo.search(
            "test-agent", "fact", user_id="user1", include_global=False
        )
        assert len(results) == 1
        assert results[0].record.user_id == "user1"

    async def test_count_user_memories(self, manager: MemoryManager) -> None:
        await manager.save(MemoryRecord(id="a", agent_id="test-agent", content="global fact"))
        await manager.save(
            MemoryRecord(id="b", agent_id="test-agent", content="user fact", user_id="user1")
        )
        assert await manager.repo.count("test-agent", user_id="user1") == 1

    async def test_delete_all_user_only(self, manager: MemoryManager) -> None:
        await manager.save(MemoryRecord(id="a", agent_id="test-agent", content="global fact"))
        await manager.save(
            MemoryRecord(id="b", agent_id="test-agent", content="user fact", user_id="user1")
        )
        deleted = await manager.repo.delete_all("test-agent", user_id="user1")
        assert deleted == 1
        # Global memory should still exist
        global_records = await manager.repo.list_memories("test-agent")
        assert len(global_records) == 1

    async def test_users_isolated_from_each_other(self, manager: MemoryManager) -> None:
        await manager.save(
            MemoryRecord(id="a", agent_id="test-agent", content="alice pref", user_id="alice")
        )
        await manager.save(
            MemoryRecord(id="b", agent_id="test-agent", content="bob pref", user_id="bob")
        )
        alice = await manager.repo.list_memories(
            "test-agent", user_id="alice", include_global=False
        )
        bob = await manager.repo.list_memories(
            "test-agent", user_id="bob", include_global=False
        )
        assert len(alice) == 1
        assert alice[0].content == "alice pref"
        assert len(bob) == 1
        assert bob[0].content == "bob pref"


class TestContextBlockLayering:
    """Test the layered context block (60% user / 40% global)."""

    async def test_global_only_when_no_user(self, manager: MemoryManager) -> None:
        await manager.save(MemoryRecord(id="a", agent_id="test-agent", content="global fact"))
        block = await manager.get_context_block("test-agent", user_id=None)
        assert "global fact" in block
        assert "User Context" not in block

    async def test_layered_sections_with_user(self, manager: MemoryManager) -> None:
        await manager.save(MemoryRecord(id="a", agent_id="test-agent", content="global fact"))
        await manager.save(
            MemoryRecord(id="b", agent_id="test-agent", content="user pref", user_id="user1")
        )
        block = await manager.get_context_block("test-agent", user_id="user1")
        assert "Agent Knowledge" in block
        assert "global fact" in block
        assert "user pref" in block

    async def test_empty_when_no_memories(self, manager: MemoryManager) -> None:
        block = await manager.get_context_block("test-agent", user_id="user1")
        assert block == ""


class TestExtractionWithUserId:
    async def test_extract_memories_with_user_id(
        self, manager: MemoryManager, llm_client: AsyncMock
    ) -> None:
        llm_client.completion.return_value = FakeLLMResponse(
            text=json.dumps(
                [{"content": "user prefers tea", "type": "semantic", "importance": 0.7}]
            )
        )
        messages = [{"role": "user", "content": "I prefer tea over coffee"}]
        records = await manager.extract_memories("test-agent", messages, user_id="user1")
        assert len(records) == 1
        assert records[0].user_id == "user1"
        assert records[0].source == MemorySource.EXTRACTED

    async def test_extract_without_user_id_is_global(
        self, manager: MemoryManager, llm_client: AsyncMock
    ) -> None:
        llm_client.completion.return_value = FakeLLMResponse(
            text=json.dumps([{"content": "agent fact", "type": "semantic", "importance": 0.5}])
        )
        messages = [{"role": "user", "content": "something"}]
        records = await manager.extract_memories("test-agent", messages, user_id=None)
        assert len(records) == 1
        assert records[0].user_id is None


class TestMemoryCompaction:
    @pytest.fixture
    def compaction_config(self) -> MemoryConfig:
        return MemoryConfig(
            enabled=True,
            compaction=CompactionConfig(
                enabled=True,
                max_memories_per_scope=5,
                compact_ratio=0.5,
                min_age_hours=0,  # Don't filter by age in tests
                importance_threshold=0.8,
                decay_factor=0.95,
            ),
        )

    @pytest.fixture
    async def compact_manager(
        self, workspace: Path, llm_client: AsyncMock, compaction_config: MemoryConfig
    ) -> MemoryManager:
        backend = FileMemoryBackend(workspace)
        await backend.initialize()
        return MemoryManager(backend=backend, llm_client=llm_client, config=compaction_config)

    async def test_no_compaction_below_threshold(self, compact_manager: MemoryManager) -> None:
        """Should not compact when memory count <= threshold."""
        for i in range(3):
            await compact_manager.save(
                MemoryRecord(id=f"m{i}", agent_id="test-agent", content=f"fact {i}")
            )
        result = await compact_manager.compact_memories("test-agent")
        assert result == 0

    async def test_compaction_triggers_above_threshold(
        self, compact_manager: MemoryManager, llm_client: AsyncMock
    ) -> None:
        """Should compact when memory count > threshold."""
        old_time = datetime.now(UTC) - timedelta(hours=48)
        for i in range(8):
            await compact_manager.save(
                MemoryRecord(
                    id=f"m{i}",
                    agent_id="test-agent",
                    content=f"old fact {i}",
                    importance=0.3,
                    created_at=old_time,
                    updated_at=old_time,
                )
            )

        llm_client.completion.return_value = FakeLLMResponse(
            text=json.dumps([{"content": "compacted summary", "importance": 0.5}])
        )

        result = await compact_manager.compact_memories("test-agent")
        assert result > 0

    async def test_compaction_preserves_recent_memories(
        self, compact_manager: MemoryManager
    ) -> None:
        """Recent memories (file backend always returns now) should not be compacted
        when min_age_hours > 0.
        """
        # Override min_age_hours to 24 — file backend records are always "now"
        compact_manager._config.compaction.min_age_hours = 24
        for i in range(8):
            await compact_manager.save(
                MemoryRecord(
                    id=f"m{i}",
                    agent_id="test-agent",
                    content=f"recent fact {i}",
                    importance=0.3,
                )
            )

        result = await compact_manager.compact_memories("test-agent")
        assert result == 0

    async def test_compaction_disabled(self, workspace: Path, llm_client: AsyncMock) -> None:
        """Should return 0 when compaction is disabled."""
        config = MemoryConfig(
            enabled=True,
            compaction=CompactionConfig(enabled=False),
        )
        backend = FileMemoryBackend(workspace)
        await backend.initialize()
        mgr = MemoryManager(backend=backend, llm_client=llm_client, config=config)
        result = await mgr.compact_memories("test-agent")
        assert result == 0

    async def test_compaction_handles_llm_failure(
        self, compact_manager: MemoryManager, llm_client: AsyncMock
    ) -> None:
        """Compaction should handle LLM failure gracefully."""
        old_time = datetime.now(UTC) - timedelta(hours=48)
        for i in range(8):
            await compact_manager.save(
                MemoryRecord(
                    id=f"m{i}",
                    agent_id="test-agent",
                    content=f"fact {i}",
                    importance=0.3,
                    created_at=old_time,
                    updated_at=old_time,
                )
            )

        llm_client.completion.side_effect = RuntimeError("LLM down")
        # Should still delete originals even if summarization fails
        result = await compact_manager.compact_memories("test-agent")
        assert result > 0


class TestRelevanceScore:
    def test_recent_memory_scores_higher(self) -> None:
        config = MemoryConfig(
            enabled=True,
            compaction=CompactionConfig(decay_factor=0.9),
        )
        backend = AsyncMock()
        mgr = MemoryManager(backend=backend, llm_client=AsyncMock(), config=config)

        now = datetime.now(UTC)
        recent = MemoryRecord(
            id="r", agent_id="a", content="recent", importance=0.5, created_at=now
        )
        old = MemoryRecord(
            id="o",
            agent_id="a",
            content="old",
            importance=0.5,
            created_at=now - timedelta(days=30),
        )

        assert mgr._relevance_score(recent, now) > mgr._relevance_score(old, now)

    def test_higher_importance_scores_higher(self) -> None:
        config = MemoryConfig(enabled=True)
        backend = AsyncMock()
        mgr = MemoryManager(backend=backend, llm_client=AsyncMock(), config=config)

        now = datetime.now(UTC)
        high = MemoryRecord(id="h", agent_id="a", content="high", importance=0.9, created_at=now)
        low = MemoryRecord(id="l", agent_id="a", content="low", importance=0.2, created_at=now)

        assert mgr._relevance_score(high, now) > mgr._relevance_score(low, now)
