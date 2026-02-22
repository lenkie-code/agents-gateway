# Memory

Agent Gateway can give agents persistent memory — facts, preferences, and context that survive across conversations. Memory is scoped to the agent and, when using a SQL backend, to individual users.

## Enabling Memory

**Globally** in `gateway.yaml`:

```yaml
memory:
  enabled: true
```

**Per-agent** in `AGENT.md` frontmatter:

```yaml
---
name: assistant
memory:
  enabled: true
---
```

The per-agent setting overrides the global one. You can enable memory globally and opt individual agents out, or keep it disabled globally and opt in selectively.

## Automatic Memory Extraction

When `auto_extract` is enabled, the Gateway automatically reads completed conversations and extracts noteworthy facts to store as memories. Extraction is debounced — it runs at most once every 30 seconds per `(agent, user)` pair to avoid excessive LLM calls.

```yaml
memory:
  enabled: true
  auto_extract: true
  extraction_model: null   # null = use the gateway's default model
```

The extraction model can be set to a different, cheaper model if you want to reduce cost. Set it to `null` to use the same model the agent uses.

## Memory Scoping

When memory is injected into an agent's context, it is drawn from two scopes:

| Scope | Budget | Contains |
|-------|--------|----------|
| User-specific | 60% of `max_injected_chars` | Memories tied to the current user |
| Global (agent-wide) | 40% of `max_injected_chars` | Memories that apply to all users |

The default `max_injected_chars` is `4000`. Adjust this to control how much memory text is prepended to each conversation.

## In-Agent Memory Tools

When memory is enabled for an agent, three tools are automatically registered and available to the LLM:

| Tool | Description |
|------|-------------|
| `recall` | Search stored memories by keyword or semantic similarity |
| `save_memory` | Store a new memory with optional importance score |
| `forget_memory` | Delete a stored memory by ID |

The agent can call these tools during a conversation — for example, saving a user preference discovered mid-conversation or recalling a fact from a previous session.

## Backends

### File-based (FileMemoryBackend)

Stores memories in a `MEMORY.md` file inside each agent's workspace directory. Human-readable, diff-friendly, and easy to pre-populate by hand.

```python
gw.use_file_memory()
```

File memory is single-user — all memories are shared across all users. It is best suited for development, personal assistants, or single-user deployments.

```yaml
memory:
  enabled: true
  max_memory_md_lines: 200
```

`max_memory_md_lines` caps the length of the `MEMORY.md` file. Compaction runs when this limit is approached.

### SQL (SqlMemoryBackend)

When a SQL persistence backend is configured, the Gateway automatically uses SQL memory storage. SQL memory supports per-user scoping, making it suitable for multi-user applications.

No additional configuration is needed — configure persistence and memory together:

```yaml
persistence:
  url: "postgresql+asyncpg://user:pass@host/db"

memory:
  enabled: true
  auto_extract: true
```

### Custom Backend

Implement the `MemoryBackend` protocol to store memories anywhere:

```python
from agent_gateway.memory import MemoryBackend

class MyMemoryBackend(MemoryBackend):
    async def save(self, memory):
        ...

    async def recall(self, agent_id, user_id, query):
        ...

    async def forget(self, memory_id):
        ...

    async def list(self, agent_id, user_id):
        ...

gw.use_memory(MyMemoryBackend())
```

## Memory Compaction

Over time, memories accumulate. Compaction automatically prunes old, low-importance, and decayed memories to keep the memory store manageable.

```yaml
memory:
  compaction:
    enabled: true
    max_memories_per_scope: 100
    compact_ratio: 0.5
    min_age_hours: 24
    importance_threshold: 0.8
    decay_factor: 0.95
```

| Setting | Default | Description |
|---------|---------|-------------|
| `enabled` | `true` | Whether compaction runs |
| `max_memories_per_scope` | `100` | Trigger compaction when a scope exceeds this count |
| `compact_ratio` | `0.5` | Fraction of memories to retain after compaction |
| `min_age_hours` | `24` | Only compact memories older than this |
| `importance_threshold` | `0.8` | Memories above this importance score are always kept |
| `decay_factor` | `0.95` | Multiplied against importance each compaction cycle |

Compaction runs in the background after extraction. It never deletes memories that are above `importance_threshold`, regardless of age.

## Configuration Reference

All memory settings in `gateway.yaml`:

```yaml
memory:
  enabled: false
  auto_extract: false
  extraction_model: null
  max_injected_chars: 4000
  max_memory_md_lines: 200
  compaction:
    enabled: true
    max_memories_per_scope: 100
    compact_ratio: 0.5
    min_age_hours: 24
    importance_threshold: 0.8
    decay_factor: 0.95
```
