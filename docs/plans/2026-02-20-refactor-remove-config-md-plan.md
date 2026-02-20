---
title: "refactor: Remove CONFIG.md, rename SOUL.md to BEHAVIOR.md"
type: refactor
status: completed
date: 2026-02-20
---

# refactor: Remove CONFIG.md, rename SOUL.md to BEHAVIOR.md

## Overview

Two related cleanups to simplify the agent file structure:

1. **Remove CONFIG.md** — all configuration already works in AGENT.md frontmatter. CONFIG.md adds merge complexity with no real benefit.
2. **Rename SOUL.md to BEHAVIOR.md** — better describes the file's purpose: defining agent guardrails and behavioral constraints.

After this refactor, an agent directory contains:
```
workspace/agents/<name>/
├── AGENT.md          # Required: prompt + frontmatter config
└── BEHAVIOR.md       # Optional: guardrails and behavior rules
```

## Problem Statement

**CONFIG.md:**
- Confusing merge semantics (lists unioned, scalars replaced)
- No real use case — env-specific overrides belong at the application level
- Zero adoption in the example project
- Maintenance burden: extra parsing, merge logic, 21 tests, extensive docs

**SOUL.md:**
- The name "soul" is vague and doesn't communicate what belongs in the file
- BEHAVIOR.md clearly signals: guardrails, behavioral rules, tone, constraints

## Proposed Solution

Hard removal of CONFIG.md. Rename SOUL.md to BEHAVIOR.md everywhere. No deprecation (pre-1.0). All configuration lives in AGENT.md frontmatter.

## Acceptance Criteria

### CONFIG.md removal
- [x] `AgentDefinition.load()` no longer reads or parses CONFIG.md
- [x] All merge logic removed from `agent.py`
- [x] Test fixture CONFIG.md deleted, content moved to AGENT.md
- [x] 3 merge/override-specific tests deleted
- [x] 18 tests updated to put config in AGENT.md frontmatter

### SOUL.md → BEHAVIOR.md rename
- [x] `agent.py` references BEHAVIOR.md instead of SOUL.md
- [x] `loader.py` references BEHAVIOR.md for root behavior file
- [x] `prompt.py` comments updated
- [x] `cli/init_cmd.py` scaffolds BEHAVIOR.md instead of SOUL.md
- [x] Field names updated: `soul_prompt` → `behavior_prompt`, `root_soul_prompt` → `root_behavior_prompt`
- [x] Example project SOUL.md renamed to BEHAVIOR.md
- [x] Test fixtures and test code updated

### Shared
- [x] Docstrings updated across all source files
- [x] CLAUDE.md updated
- [x] DESIGN.md updated
- [x] All tests pass (`uv run pytest -m "not e2e"`)
- [x] Example project still works (`make dev`)

## Implementation Phases

### Phase 1: Remove CONFIG.md logic

**File: `src/agent_gateway/workspace/agent.py`**

1. Remove CONFIG.md parsing block (~lines 82-87):
   ```python
   # DELETE: config_path, config_parsed, config_meta logic
   ```

2. Simplify all field reads to use `agent_meta` only (~lines 89-123):
   ```python
   # BEFORE:
   skills = list(dict.fromkeys(agent_meta.get("skills", []) + config_meta.get("skills", [])))
   tools = list(dict.fromkeys(agent_meta.get("tools", []) + config_meta.get("tools", [])))
   model_raw = config_meta.get("model") or agent_meta.get("model", {})
   execution_mode = config_meta.get("execution_mode") or agent_meta.get("execution_mode", "sync")

   # AFTER:
   skills = agent_meta.get("skills", [])
   tools = agent_meta.get("tools", [])
   model_raw = agent_meta.get("model", {})
   execution_mode = agent_meta.get("execution_mode", "sync")
   ```

3. Update module docstring and `AgentModelConfig` docstring — remove CONFIG.md references.

### Phase 2: Rename SOUL.md → BEHAVIOR.md

**File: `src/agent_gateway/workspace/agent.py`**

1. Rename field `soul_prompt` → `behavior_prompt` in `AgentDefinition` dataclass
2. Change file reference from `SOUL.md` to `BEHAVIOR.md` in `load()`

**File: `src/agent_gateway/workspace/loader.py`**

1. Rename field `root_soul_prompt` → `root_behavior_prompt` in `WorkspaceState`
2. Change root file reference from `agents/SOUL.md` to `agents/BEHAVIOR.md`

**File: `src/agent_gateway/workspace/prompt.py`**

1. Update field references from `soul_prompt` → `behavior_prompt`
2. Update `root_soul_prompt` → `root_behavior_prompt`
3. Update comments describing prompt assembly order

**File: `src/agent_gateway/cli/init_cmd.py`**

1. Change scaffolded filename from `SOUL.md` to `BEHAVIOR.md`
2. Update content heading from `# SOUL` to `# BEHAVIOR`

### Phase 3: Test fixture updates

**CONFIG.md removal:**
- **Delete:** `tests/fixtures/workspace/agents/test-agent/CONFIG.md`
- **Update:** `tests/fixtures/workspace/agents/test-agent/AGENT.md` — add `tools: [echo]` to frontmatter

**SOUL.md rename:**
- **Rename:** `examples/test-project/workspace/agents/assistant/SOUL.md` → `BEHAVIOR.md`
- Update content heading from `# SOUL` to `# BEHAVIOR`

### Phase 4: Test updates

**Delete these 3 tests** (CONFIG.md merge/override behavior no longer exists):

| File | Test |
|------|------|
| `tests/test_workspace/test_agent.py` | `test_frontmatter_merge_agent_and_config` |
| `tests/test_workspace/test_agent_input_schema.py` | `test_input_schema_in_config_md_overrides` |
| `tests/test_queue/test_execution_mode.py` | `test_execution_mode_config_md_overrides_agent_md` |

**Rewrite 18 tests** — move CONFIG.md frontmatter into AGENT.md:

| File | Tests |
|------|-------|
| `tests/test_workspace/test_agent.py` | `test_load_full_agent`, `test_agent_with_schedules`, `test_agent_with_invalid_schedule`, `test_agent_with_model_config` |
| `tests/test_notifications/test_agent_config.py` | 8 tests (all except `test_notifications_in_agent_md_frontmatter`) |
| `tests/test_workspace/test_loader.py` | `test_cross_reference_warnings`, `test_schedules_collected` |
| `tests/test_workspace/test_prompt.py` | `test_skills_injected`, `test_missing_skill_skipped` |
| `tests/test_cli/test_check.py` | `test_check_reports_warnings` |
| `tests/test_cli/test_list.py` | `test_schedules_with_schedule_data` |

**Update SOUL.md → BEHAVIOR.md in tests:**

| File | Changes |
|------|---------|
| `tests/test_workspace/test_agent.py` | `test_load_full_agent` — change `SOUL.md` → `BEHAVIOR.md` |
| `tests/test_workspace/test_prompt.py` | Update `SOUL.md` file writes to `BEHAVIOR.md`, update field references |
| `tests/test_workspace/test_loader.py` | Update root `SOUL.md` → `BEHAVIOR.md` |
| `tests/test_cli/test_init.py` | Assert `BEHAVIOR.md` exists instead of `SOUL.md` |

### Phase 5: Docstring updates

Update CONFIG.md and SOUL.md references across source files:

| File | Lines | Change |
|------|-------|--------|
| `src/agent_gateway/gateway.py` | ~809, ~813 | CONFIG.md → AGENT.md frontmatter |
| `src/agent_gateway/notifications/models.py` | ~31, ~71 | CONFIG.md → AGENT.md frontmatter |
| `src/agent_gateway/notifications/backends/slack.py` | ~88 | CONFIG.md → AGENT.md frontmatter |
| `src/agent_gateway/notifications/backends/webhook.py` | ~93 | CONFIG.md → AGENT.md frontmatter |

### Phase 6: Documentation

**`CLAUDE.md`** — Update "Key Conventions":
```
- Before: Agents defined in workspace/agents/<name>/ with AGENT.md + optional SOUL.md/CONFIG.md. CONFIG.md overrides AGENT.md scalars; lists are merged
- After:  Agents defined in workspace/agents/<name>/ with AGENT.md + optional BEHAVIOR.md
```

**`DESIGN.md`** — Larger update:
- Remove section 6.3 ("CONFIG.md — Agent Settings")
- Rename section 6.2 from "SOUL.md" to "BEHAVIOR.md"
- Update all workspace directory trees
- Update prompt assembly order descriptions
- Update all examples and flow descriptions
- Replace all SOUL.md references with BEHAVIOR.md
- Replace all CONFIG.md references

**`examples/test-project/README.md`** — Update directory tree showing SOUL.md → BEHAVIOR.md

**`docs/plans/`** — Leave as-is (historical documents).

## Risk Analysis

**Low risk.** Both changes are well-scoped:
- CONFIG.md removal: only `agent.py` has behavioral changes
- SOUL.md rename: straightforward find-and-replace across a small surface area
- Every feature already works in AGENT.md frontmatter
- Comprehensive test suite catches regressions
- Pre-1.0 project with no backward-compatibility obligation

**Footgun to avoid:** When simplifying `config_meta.get("model") or agent_meta.get("model", {})` to `agent_meta.get("model", {})`, keep the default values (`{}`, `[]`, `"sync"`, etc.) intact.

## References

- Core parsing: `src/agent_gateway/workspace/agent.py:56-141`
- Prompt assembly: `src/agent_gateway/workspace/prompt.py`
- Workspace loader: `src/agent_gateway/workspace/loader.py`
- CLI init: `src/agent_gateway/cli/init_cmd.py`
- Markdown parser: `src/agent_gateway/workspace/parser.py:25-57`
- Test fixture: `tests/fixtures/workspace/agents/test-agent/`
- Example agents: `examples/test-project/workspace/agents/`
