"""MemoryManager — orchestrates memory with LLM-powered extraction."""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from agent_gateway.memory.domain import (
    MemoryRecord,
    MemorySearchResult,
    MemorySource,
    MemoryType,
)
from agent_gateway.memory.protocols import MemoryBackend, MemoryRepository

if TYPE_CHECKING:
    from agent_gateway.config import MemoryConfig
    from agent_gateway.engine.llm import LLMClient

logger = logging.getLogger(__name__)

_DEFAULT_EXTRACTION_PROMPT = """\
You are a memory extraction system. Given the following conversation between \
a user and an AI agent, extract discrete, important facts worth remembering \
for future conversations.

Rules:
- Extract facts, preferences, decisions, and outcomes
- Each memory should be a single, self-contained statement
- Classify each as: episodic (what happened), semantic (facts/knowledge), \
or procedural (how to do something)
- Rate importance from 0.0 to 1.0 (only extract items >= 0.3)
- Do NOT extract trivial pleasantries or obvious context
- Synthesize — don't quote verbatim. "User prefers dark mode" not \
"The user said 'I like dark mode'"
- If a fact contradicts an existing memory, note the update

{existing_memories_section}

Respond with ONLY a JSON array (no markdown fences):
[{{"content": "...", "type": "semantic|episodic|procedural", "importance": 0.7}}]

If there is nothing worth remembering, respond with an empty array: []"""

_COMPACTION_PROMPT = """\
You are a memory compaction system. Given the following group of related \
memories, synthesize them into fewer, more concise memories that preserve \
the essential information.

Rules:
- Combine redundant or overlapping memories into single statements
- Preserve important details, preferences, and decisions
- Each output memory should be self-contained
- Maintain the memory type classification ({memory_type})
- Rate importance based on the most important input memory
- Aim for roughly {target_count} output memories

Input memories:
{memories}

Respond with ONLY a JSON array (no markdown fences):
[{{"content": "...", "importance": 0.7}}]"""


class MemoryManager:
    """Orchestrates memory operations with LLM-powered extraction and compaction."""

    def __init__(
        self,
        backend: MemoryBackend,
        llm_client: LLMClient,
        config: MemoryConfig,
    ) -> None:
        self._backend = backend
        self._llm = llm_client
        self._config = config

    async def dispose(self) -> None:
        """Dispose the underlying memory backend."""
        await self._backend.dispose()

    @property
    def repo(self) -> MemoryRepository:
        return self._backend.memory_repo

    # ── Core CRUD (delegates to repo) ────────────────────────────────

    async def save(self, record: MemoryRecord) -> None:
        """Save a memory record."""
        await self._backend.memory_repo.save(record)

    async def get(self, agent_id: str, memory_id: str) -> MemoryRecord | None:
        return await self._backend.memory_repo.get(agent_id, memory_id)

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
        return await self._backend.memory_repo.search(
            agent_id,
            query,
            user_id=user_id,
            include_global=include_global,
            memory_type=memory_type,
            limit=limit,
        )

    async def delete(self, agent_id: str, memory_id: str) -> bool:
        return await self._backend.memory_repo.delete(agent_id, memory_id)

    # ── LLM-Powered Operations ───────────────────────────────────────

    async def extract_memories(
        self,
        agent_id: str,
        messages: list[dict[str, Any]],
        user_id: str | None = None,
    ) -> list[MemoryRecord]:
        """Extract memorable facts from a conversation using the LLM.

        Deduplicates against existing memories before saving.
        When user_id is provided, extracted memories are scoped to that user.
        """
        # Get existing memories for dedup context (user + global)
        existing = await self._backend.memory_repo.list_memories(
            agent_id, user_id=user_id, include_global=True, limit=50
        )
        existing_section = ""
        if existing:
            existing_lines = [f"- {r.content}" for r in existing]
            existing_section = "Existing memories (do not duplicate these):\n" + "\n".join(
                existing_lines
            )

        system_prompt = _DEFAULT_EXTRACTION_PROMPT.format(
            existing_memories_section=existing_section
        )

        extraction_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": _format_conversation_for_extraction(messages),
            },
        ]

        try:
            response = await self._llm.completion(
                messages=extraction_messages,
                model=self._config.extraction_model,
                temperature=0.1,
            )
        except Exception:
            logger.warning(
                "Memory extraction failed for agent '%s'",
                agent_id,
                exc_info=True,
            )
            return []

        records = _parse_extraction_response(response.text or "[]", agent_id, user_id=user_id)

        # Save extracted records
        for record in records:
            await self._backend.memory_repo.save(record)

        if records:
            logger.info(
                "Extracted %d memories for agent '%s'",
                len(records),
                agent_id,
            )

        return records

    async def get_context_block(
        self,
        agent_id: str,
        query: str | None = None,
        max_chars: int | None = None,
        user_id: str | None = None,
    ) -> str:
        """Build the memory block for prompt injection.

        If user_id is provided, builds a layered block:
        - 60% budget for per-user memories
        - 40% budget for global agent memories
        """
        max_chars = max_chars or self._config.max_injected_chars
        blocks: list[str] = []

        if user_id:
            user_budget = int(max_chars * 0.6)
            global_budget = max_chars - user_budget

            # Per-user memories
            user_block = await self._build_memory_section(
                agent_id, query, user_budget, user_id=user_id, include_global=False
            )
            if user_block:
                blocks.append(f"### User Context\n{user_block}")

            # Global agent memories
            global_block = await self._build_memory_section(
                agent_id, query, global_budget, user_id=None, include_global=True
            )
            if global_block:
                blocks.append(f"### Agent Knowledge\n{global_block}")
        else:
            # No user context — just global memories
            global_block = await self._build_memory_section(
                agent_id, query, max_chars, user_id=None, include_global=True
            )
            if global_block:
                blocks.append(global_block)

        return "\n\n".join(blocks)

    # ── Memory Compaction ───────────────────────────────────────────

    async def compact_memories(
        self,
        agent_id: str,
        user_id: str | None = None,
    ) -> int:
        """Compact memories for a given scope. Returns number of memories removed."""
        compaction = self._config.compaction
        if not compaction.enabled:
            return 0

        count = await self._backend.memory_repo.count(agent_id, user_id)
        if count <= compaction.max_memories_per_scope:
            return 0

        # Fetch all memories for this scope
        memories = await self._backend.memory_repo.list_memories(
            agent_id,
            user_id=user_id,
            include_global=user_id is None,
            limit=count,
        )

        now = datetime.now(UTC)
        scored = [(m, self._relevance_score(m, now)) for m in memories]

        # Protect high-importance and recent memories
        min_age = timedelta(hours=compaction.min_age_hours)
        compactable = [
            (m, s)
            for m, s in scored
            if m.importance < compaction.importance_threshold and m.created_at < now - min_age
        ]

        # Sort by score ascending (least relevant first)
        compactable.sort(key=lambda x: x[1])

        # Take bottom N for compaction
        to_compact = compactable[: int(len(compactable) * compaction.compact_ratio)]
        if not to_compact:
            return 0

        # Group by memory_type and summarize each group via LLM
        groups: dict[MemoryType, list[MemoryRecord]] = defaultdict(list)
        for m, _ in to_compact:
            groups[m.memory_type].append(m)

        for memory_type, group_memories in groups.items():
            summary_records = await self._summarize_memories(
                group_memories, agent_id, memory_type, user_id=user_id
            )
            for sr in summary_records:
                await self._backend.memory_repo.save(sr)

            # Delete the originals
            for m in group_memories:
                await self._backend.memory_repo.delete(agent_id, m.id)

        compacted_count = len(to_compact)
        logger.info(
            "Compacted %d memories for agent '%s' (user=%s)",
            compacted_count,
            agent_id,
            user_id or "global",
        )
        return compacted_count

    def _relevance_score(self, record: MemoryRecord, now: datetime) -> float:
        """Score a memory by importance * time-decay.

        Decay is applied per day since last access (or creation if never accessed).
        """
        decay_factor = self._config.compaction.decay_factor
        reference_time = record.last_accessed_at or record.created_at
        days_since = max(0.0, (now - reference_time).total_seconds() / 86400)
        return float(record.importance * (decay_factor**days_since))

    async def _summarize_memories(
        self,
        memories: list[MemoryRecord],
        agent_id: str,
        memory_type: MemoryType,
        user_id: str | None = None,
    ) -> list[MemoryRecord]:
        """Use LLM to synthesize a group of memories into fewer summaries."""
        memory_lines = "\n".join(f"- {m.content}" for m in memories)
        target_count = max(1, len(memories) // 3)

        prompt = _COMPACTION_PROMPT.format(
            memory_type=memory_type.value,
            target_count=target_count,
            memories=memory_lines,
        )

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self._llm.completion(
                messages=messages,
                model=self._config.extraction_model,
                temperature=0.1,
            )
        except Exception:
            logger.warning(
                "Memory compaction summarization failed for agent '%s'",
                agent_id,
                exc_info=True,
            )
            return []

        # Reuse the extraction response parser with COMPACTED source
        return _parse_extraction_response(
            response.text or "[]",
            agent_id,
            source=MemorySource.COMPACTED,
            user_id=user_id,
        )

    async def _build_memory_section(
        self,
        agent_id: str,
        query: str | None,
        max_chars: int,
        user_id: str | None = None,
        include_global: bool = True,
    ) -> str:
        """Build a memory section from search or list results.

        Uses query-based search when available, falling back to listing
        recent memories when search yields no results.
        """
        records: list[MemoryRecord] = []
        if query:
            results = await self._backend.memory_repo.search(
                agent_id, query, user_id=user_id, include_global=include_global, limit=20
            )
            records = [r.record for r in results]

        # Fall back to recent memories when search returns nothing
        if not records:
            records = await self._backend.memory_repo.list_memories(
                agent_id, user_id=user_id, include_global=include_global, limit=50
            )

        if not records:
            return ""

        lines: list[str] = []
        total_chars = 0
        for r in records:
            line = f"- [{r.memory_type.value}] {r.content}"
            if total_chars + len(line) > max_chars:
                break
            lines.append(line)
            total_chars += len(line)

        return "\n".join(lines)


def _format_conversation_for_extraction(messages: list[dict[str, Any]]) -> str:
    """Format conversation messages for the extraction prompt."""
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _parse_extraction_response(
    text: str,
    agent_id: str,
    source: MemorySource = MemorySource.EXTRACTED,
    user_id: str | None = None,
) -> list[MemoryRecord]:
    """Parse the LLM's JSON array response into MemoryRecords."""
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        # Remove first and last lines (fences)
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        items = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse memory extraction response: %s", text[:200])
        return []

    if not isinstance(items, list):
        logger.warning("Memory extraction response is not a list")
        return []

    now = datetime.now(UTC)
    records: list[MemoryRecord] = []
    for item in items:
        if not isinstance(item, dict) or "content" not in item:
            continue

        raw_type = item.get("type", "semantic")
        try:
            memory_type = MemoryType(raw_type)
        except ValueError:
            memory_type = MemoryType.SEMANTIC

        importance = float(item.get("importance", 0.5))
        importance = max(0.0, min(1.0, importance))

        records.append(
            MemoryRecord(
                id=uuid.uuid4().hex[:12],
                agent_id=agent_id,
                content=item["content"],
                user_id=user_id,
                memory_type=memory_type,
                source=source,
                importance=importance,
                created_at=now,
                updated_at=now,
            )
        )

    return records
