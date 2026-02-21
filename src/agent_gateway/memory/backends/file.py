"""File-based memory backend using MEMORY.md per agent + per-user files.

Stores memories as structured markdown sections grouped by type.
Zero infrastructure — human-readable, git-committable, inspectable.

Layout:
    workspace/agents/{agent_id}/MEMORY.md              — agent-level (global) memories
    workspace/agents/{agent_id}/memory/{user_id}.md    — per-user memories
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from agent_gateway.memory.domain import (
    MemoryRecord,
    MemorySearchResult,
    MemorySource,
    MemoryType,
)

logger = logging.getLogger(__name__)

_SECTION_HEADING = re.compile(r"^## (Semantic|Episodic|Procedural)\s*$")
_MEMORY_LINE = re.compile(
    r"^- (?:\[([^\]]+)\] )?(.+)$"  # optional [id] prefix, then content
)

_SAFE_AGENT_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
_SAFE_FILENAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.@-]*$")

_TYPE_TO_HEADING: dict[MemoryType, str] = {
    MemoryType.SEMANTIC: "Semantic",
    MemoryType.EPISODIC: "Episodic",
    MemoryType.PROCEDURAL: "Procedural",
}
_HEADING_TO_TYPE: dict[str, MemoryType] = {v: k for k, v in _TYPE_TO_HEADING.items()}


def _user_filename(user_id: str) -> str:
    """Derive a safe filename from a user_id.

    If the user_id is already filesystem-safe (e.g. 'alice'), use it directly.
    Otherwise hash it to avoid path traversal or special characters.
    """
    if _SAFE_FILENAME.match(user_id) and len(user_id) <= 100:
        return f"{user_id}.md"
    hashed = hashlib.sha256(user_id.encode()).hexdigest()[:16]
    return f"user-{hashed}.md"


class FileMemoryRepository:
    """Repository that reads/writes structured markdown files.

    Supports both agent-level (global) and per-user memory files.

    .. note::
        All file I/O is synchronous (stdlib ``pathlib``/``open``).  This is
        intentional for the default zero-dependency backend: memory operations
        are infrequent and the files are small (< 100 KB).  For
        high-throughput scenarios, swap in an async backend (e.g. pgvector)
        via ``gateway.set_memory_backend()``.
    """

    def __init__(self, workspace_root: Path, max_lines: int = 200) -> None:
        self._root = workspace_root
        self._max_lines = max_lines
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _agent_dir(self, agent_id: str) -> Path:
        if not _SAFE_AGENT_ID.match(agent_id):
            raise ValueError(f"Invalid agent_id: {agent_id!r}")
        path = self._root / "agents" / agent_id
        if not path.resolve().is_relative_to(self._root.resolve()):
            raise ValueError(f"Path traversal detected for agent_id: {agent_id!r}")
        return path

    def _global_memory_path(self, agent_id: str) -> Path:
        return self._agent_dir(agent_id) / "MEMORY.md"

    def _user_memory_path(self, agent_id: str, user_id: str) -> Path:
        agent_dir = self._agent_dir(agent_id)
        path = agent_dir / "memory" / _user_filename(user_id)
        if not path.resolve().is_relative_to(agent_dir.resolve()):
            raise ValueError(f"Path traversal detected for user_id: {user_id!r}")
        return path

    def _memory_path(self, agent_id: str, user_id: str | None = None) -> Path:
        if user_id is not None:
            return self._user_memory_path(agent_id, user_id)
        return self._global_memory_path(agent_id)

    def _lock_key(self, agent_id: str, user_id: str | None = None) -> str:
        if user_id is not None:
            return f"{agent_id}:user:{user_id}"
        return agent_id

    def _parse_file(
        self, path: Path, agent_id: str, user_id: str | None = None
    ) -> list[MemoryRecord]:
        """Parse a MEMORY.md file into MemoryRecord objects."""
        if not path.exists():
            return []

        content = path.read_text(encoding="utf-8")
        records: list[MemoryRecord] = []
        current_type = MemoryType.SEMANTIC
        now = datetime.now(UTC)

        for line in content.splitlines():
            heading_match = _SECTION_HEADING.match(line)
            if heading_match:
                current_type = _HEADING_TO_TYPE[heading_match.group(1)]
                continue

            mem_match = _MEMORY_LINE.match(line)
            if mem_match:
                memory_id = mem_match.group(1) or uuid.uuid4().hex[:8]
                memory_content = mem_match.group(2)
                records.append(
                    MemoryRecord(
                        id=memory_id,
                        agent_id=agent_id,
                        content=memory_content,
                        memory_type=current_type,
                        source=MemorySource.MANUAL,
                        user_id=user_id,
                        created_at=now,
                        updated_at=now,
                    )
                )

        return records

    def _write_records(self, path: Path, records: list[MemoryRecord]) -> None:
        """Write records to a memory file as structured markdown."""
        path.parent.mkdir(parents=True, exist_ok=True)

        grouped: dict[MemoryType, list[MemoryRecord]] = {
            MemoryType.SEMANTIC: [],
            MemoryType.EPISODIC: [],
            MemoryType.PROCEDURAL: [],
        }
        for r in records:
            grouped[r.memory_type].append(r)

        lines: list[str] = []
        for mem_type, heading in _TYPE_TO_HEADING.items():
            type_records = grouped[mem_type]
            if not type_records:
                continue
            lines.append(f"## {heading}")
            for r in type_records:
                lines.append(f"- [{r.id}] {r.content}")
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")

    async def save(self, record: MemoryRecord) -> None:
        key = self._lock_key(record.agent_id, record.user_id)
        path = self._memory_path(record.agent_id, record.user_id)
        async with self._lock_for(key):
            records = self._parse_file(path, record.agent_id, record.user_id)

            # Upsert: replace existing record with same id
            found = False
            for i, r in enumerate(records):
                if r.id == record.id:
                    records[i] = record
                    found = True
                    break

            if not found:
                records.append(record)

            self._write_records(path, records)

    async def get(self, agent_id: str, memory_id: str) -> MemoryRecord | None:
        # Search global first, then all user files
        global_records = self._parse_file(self._global_memory_path(agent_id), agent_id)
        for r in global_records:
            if r.id == memory_id:
                return r

        user_dir = self._agent_dir(agent_id) / "memory"
        if user_dir.exists():
            for user_file in user_dir.glob("*.md"):
                user_records = self._parse_file(user_file, agent_id)
                for r in user_records:
                    if r.id == memory_id:
                        return r
        return None

    async def list_memories(
        self,
        agent_id: str,
        *,
        user_id: str | None = None,
        include_global: bool = True,
        memory_type: MemoryType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []

        # Include user-specific memories
        if user_id is not None:
            user_path = self._user_memory_path(agent_id, user_id)
            records.extend(self._parse_file(user_path, agent_id, user_id))

        # Include global memories
        if include_global or user_id is None:
            global_path = self._global_memory_path(agent_id)
            records.extend(self._parse_file(global_path, agent_id))

        if memory_type is not None:
            records = [r for r in records if r.memory_type == memory_type]
        # Most recent first (by position in file, newest appended last)
        records.reverse()
        return records[offset : offset + limit]

    async def search(
        self,
        agent_id: str,
        query: str,
        *,
        user_id: str | None = None,
        include_global: bool = True,
        memory_type: MemoryType | None = None,
        limit: int = 10,
    ) -> list[MemorySearchResult]:
        """Simple keyword search — case-insensitive matching."""
        records: list[MemoryRecord] = []

        if user_id is not None:
            user_path = self._user_memory_path(agent_id, user_id)
            records.extend(self._parse_file(user_path, agent_id, user_id))

        if include_global or user_id is None:
            global_path = self._global_memory_path(agent_id)
            records.extend(self._parse_file(global_path, agent_id))

        if memory_type is not None:
            records = [r for r in records if r.memory_type == memory_type]

        query_lower = query.lower()
        query_words = query_lower.split()

        results: list[MemorySearchResult] = []
        for r in records:
            content_lower = r.content.lower()
            # Score: fraction of query words found in content
            matches = sum(1 for w in query_words if w in content_lower)
            if matches > 0:
                score = matches / len(query_words) if query_words else 0.0
                # Boost user-specific memories when searching with user context
                if user_id is not None and r.user_id == user_id:
                    score *= 1.2
                results.append(MemorySearchResult(record=r, score=score))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    async def delete(self, agent_id: str, memory_id: str) -> bool:
        # Try global file first
        global_path = self._global_memory_path(agent_id)
        key = self._lock_key(agent_id)
        async with self._lock_for(key):
            records = self._parse_file(global_path, agent_id)
            original_count = len(records)
            records = [r for r in records if r.id != memory_id]
            if len(records) < original_count:
                self._write_records(global_path, records)
                return True

        # Try user files
        user_dir = self._agent_dir(agent_id) / "memory"
        if user_dir.exists():
            for user_file in user_dir.glob("*.md"):
                user_key = f"{agent_id}:file:{user_file.name}"
                async with self._lock_for(user_key):
                    user_records = self._parse_file(user_file, agent_id)
                    original_count = len(user_records)
                    user_records = [r for r in user_records if r.id != memory_id]
                    if len(user_records) < original_count:
                        self._write_records(user_file, user_records)
                        return True
        return False

    async def delete_all(self, agent_id: str, user_id: str | None = None) -> int:
        if user_id is not None:
            # Delete only this user's memories
            user_path = self._user_memory_path(agent_id, user_id)
            key = self._lock_key(agent_id, user_id)
            async with self._lock_for(key):
                records = self._parse_file(user_path, agent_id, user_id)
                count = len(records)
                if count > 0:
                    user_path.write_text("", encoding="utf-8")
                return count

        # Delete all memories (global + all user files)
        total = 0
        global_path = self._global_memory_path(agent_id)
        key = self._lock_key(agent_id)
        async with self._lock_for(key):
            records = self._parse_file(global_path, agent_id)
            total += len(records)
            if records:
                global_path.write_text("", encoding="utf-8")

        user_dir = self._agent_dir(agent_id) / "memory"
        if user_dir.exists():
            for user_file in user_dir.glob("*.md"):
                user_key = f"{agent_id}:file:{user_file.name}"
                async with self._lock_for(user_key):
                    user_records = self._parse_file(user_file, agent_id)
                    total += len(user_records)
                    if user_records:
                        user_file.write_text("", encoding="utf-8")

        return total

    async def count(self, agent_id: str, user_id: str | None = None) -> int:
        if user_id is not None:
            user_path = self._user_memory_path(agent_id, user_id)
            return len(self._parse_file(user_path, agent_id, user_id))

        # Count all (global + all user files)
        total = len(self._parse_file(self._global_memory_path(agent_id), agent_id))
        user_dir = self._agent_dir(agent_id) / "memory"
        if user_dir.exists():
            for user_file in user_dir.glob("*.md"):
                total += len(self._parse_file(user_file, agent_id))
        return total


class FileMemoryBackend:
    """File-based memory backend using MEMORY.md per agent + per-user files.

    Zero-config default. Stores memories as structured markdown sections
    grouped by type. Supports keyword search and per-agent asyncio locks.
    """

    def __init__(self, workspace_root: str | Path, max_lines: int = 200) -> None:
        self._root = Path(workspace_root)
        self._max_lines = max_lines
        self._repo = FileMemoryRepository(self._root, max_lines)

    async def initialize(self) -> None:
        pass

    async def dispose(self) -> None:
        pass

    @property
    def memory_repo(self) -> FileMemoryRepository:
        return self._repo
