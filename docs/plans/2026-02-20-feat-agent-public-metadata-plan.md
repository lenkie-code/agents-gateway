---
title: "feat: Add public-facing metadata to agents"
type: feat
status: completed
date: 2026-02-20
---

# Add Public-Facing Agent Metadata

## Overview

The agent introspection API (`GET /v1/agents`, `GET /v1/agents/{id}`) currently exposes the agent's prompt by truncating `agent_prompt[:200]` as the `description` field. This leaks internal implementation details. We need dedicated frontmatter fields (`description`, `display_name`, `tags`, `version`) so agents present a clean public identity, and the prompt is never exposed through the API.

## Problem Statement

- `AgentInfo.description` is derived from `agent.agent_prompt[:200]` — a truncation of the full system prompt
- There is no way for agent authors to control what consumers see about their agents
- No support for display names, tags, or versioning metadata
- The prompt is an internal implementation detail that should not be visible to API consumers

## Proposed Solution

Add four new optional frontmatter fields to `AGENT.md`:

```yaml
description: "Plans multi-day travel itineraries with budget optimization"
display_name: "Travel Planner"
tags: ["travel", "planning"]
version: "1.0.0"
```

These flow through the existing pipeline: frontmatter → `AgentDefinition` → `AgentInfo` → API response. The `agent_prompt` field is never serialized to any API response.

## Technical Approach

### 1. Update `AgentDefinition` dataclass

**File:** `src/agent_gateway/workspace/agent.py`

Add fields to the dataclass:

```python
@dataclass
class AgentDefinition:
    id: str
    path: Path
    agent_prompt: str
    behavior_prompt: str = ""
    description: str = ""           # NEW
    display_name: str | None = None # NEW
    tags: list[str] = field(default_factory=list)  # NEW
    version: str | None = None      # NEW
    # ... existing fields unchanged
```

### 2. Update frontmatter parsing in `AgentDefinition.load()`

**File:** `src/agent_gateway/workspace/agent.py`

Follow the existing `.get()` pattern with type validation and warnings:

```python
# Parse public metadata
description = agent_meta.get("description", "")
if not isinstance(description, str):
    logger.warning("Agent '%s': 'description' must be a string, ignoring", agent_id)
    description = ""

display_name = agent_meta.get("display_name", None)
if display_name is not None and not isinstance(display_name, str):
    logger.warning("Agent '%s': 'display_name' must be a string, ignoring", agent_id)
    display_name = None

tags = agent_meta.get("tags", [])
if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
    logger.warning("Agent '%s': 'tags' must be a list of strings, ignoring", agent_id)
    tags = []

version = agent_meta.get("version", None)
if version is not None:
    version = str(version)  # coerce numeric versions like 1.0
```

### 3. Update `AgentInfo` Pydantic response model

**File:** `src/agent_gateway/api/models.py`

```python
class AgentInfo(BaseModel):
    id: str
    description: str = ""
    display_name: str | None = None              # NEW
    tags: list[str] = Field(default_factory=list) # NEW
    version: str | None = None                    # NEW
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    model: str | None = None
    schedules: list[str] = Field(default_factory=list)
    execution_mode: str = "sync"
    notifications: NotificationConfigInfo | None = None
    input_schema: dict[str, Any] | None = None
```

### 4. Update introspection route handlers

**File:** `src/agent_gateway/api/routes/introspection.py`

Replace the prompt-based description with the new metadata fields:

```python
# Before (line ~66 and ~100):
description=agent.agent_prompt[:200]

# After:
description=agent.description if agent.description else f"Agent: {agent.id}"
display_name=agent.display_name,
tags=agent.tags,
version=agent.version,
```

The fallback `f"Agent: {agent.id}"` is used when no description is provided, generating a readable default from the agent's directory name.

### 5. Update example project agents

**File:** `examples/test-project/workspace/agents/*/AGENT.md`

Add metadata to all four agents. At least two agents should have all fields populated; the others can be minimal to exercise default/fallback paths.

**travel-planner** (full metadata):
```yaml
description: "Plans multi-day travel itineraries with budget optimization and local recommendations"
display_name: "Travel Planner"
tags: ["travel", "planning", "budgeting"]
version: "1.0.0"
```

**assistant** (full metadata):
```yaml
description: "General-purpose assistant with math and utility skills"
display_name: "Assistant"
tags: ["general", "math"]
version: "1.0.0"
```

**data-processor** (minimal — no description, to test fallback):
```yaml
display_name: "Data Processor"
tags: ["data", "async"]
```

**scheduled-reporter** (minimal — no metadata, to test all defaults):
No changes needed — exercises the fully-defaulted path.

### 6. Add tests

**File:** `tests/workspace/test_agent.py` (or existing test file)

- Parse AGENT.md with all four new fields → verify `AgentDefinition` fields
- Parse AGENT.md with no new fields → verify defaults (`description=""`, `display_name=None`, `tags=[]`, `version=None`)
- Parse AGENT.md with invalid types (e.g., `tags: "not-a-list"`) → verify warning logged and defaults used
- Numeric version coercion: `version: 1.0` → `"1.0"`

**File:** `tests/api/test_introspection.py` (new or extend existing)

- `GET /v1/agents` returns list with `display_name`, `tags`, `version` fields
- `GET /v1/agents/{id}` returns agent with correct metadata
- Verify `agent_prompt` content does NOT appear in any response field
- Agent with no description returns `"Agent: {id}"` fallback
- Agent with description returns the authored description

## Acceptance Criteria

- [x] `AGENT.md` frontmatter supports `description`, `display_name`, `tags`, `version`
- [x] `AgentDefinition` stores all four new fields with sensible defaults
- [x] Invalid frontmatter types log warnings and fall back to defaults
- [x] `AgentInfo` API response includes `display_name`, `tags`, `version`
- [x] `description` uses authored value or auto-generates from id — never truncated prompt
- [x] `agent_prompt` is never exposed in any API response
- [x] Example project demonstrates new metadata fields
- [x] Unit tests cover parsing (valid, missing, invalid types)
- [x] API tests verify response shape and prompt non-exposure
- [x] `uv run pytest -m "not e2e"` passes
- [x] `uv run ruff check src/ tests/` passes
- [x] `uv run mypy src/` passes

## Out of Scope

- Tag-based filtering on `GET /v1/agents` (follow-up feature)
- Version comparison or semver enforcement (version is a free-form string)
- Prompt access via separate endpoint or query parameter
- Audit of `agent_prompt` in logs or internal prompt assembly (scope is API surface only)

## Dependencies & Risks

- **Non-breaking API change**: Adding fields to JSON responses is additive. However, `description` changes semantics from prompt-excerpt to authored metadata — consumers relying on the old content will see different values.
- **Migration**: Existing agents without the new fields will get defaults. The `"Agent: {id}"` fallback ensures descriptions are never empty.

## References

- `src/agent_gateway/workspace/agent.py` — `AgentDefinition` dataclass and `load()` method
- `src/agent_gateway/api/models.py:112-123` — `AgentInfo` Pydantic model
- `src/agent_gateway/api/routes/introspection.py:66,100` — prompt truncation lines
- `src/agent_gateway/workspace/parser.py` — frontmatter parsing with `python-frontmatter`
