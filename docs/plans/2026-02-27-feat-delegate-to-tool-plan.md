---
title: "feat: Make delegate_to_agent a built-in tool for all agents"
type: feat
status: active
date: 2026-02-27
---

# Make `delegate_to_agent` a Built-in Tool for All Agents

## Overview

Currently, the `delegate_to_agent` tool is only registered for agents that have an explicit `delegates_to` list in their AGENT.md frontmatter. This plan changes delegation to be a **built-in tool available to every agent automatically**, while preserving the ability to restrict delegation targets via `delegates_to` when desired.

## Problem Statement

Today, inter-agent delegation requires upfront configuration: a coordinator must list every agent it can delegate to in `delegates_to`. This is limiting because:

1. **Rigid orchestration**: Adding a new specialist agent requires updating every coordinator's frontmatter.
2. **No emergent collaboration**: Agents cannot discover and delegate to peers dynamically based on the task.
3. **All-or-nothing**: An agent either has the delegation tool (with a fixed allow-list) or does not have it at all.

## Proposed Solution

Make `delegate_to_agent` a built-in tool registered for **all** agents in every workspace that has more than one agent. When `delegates_to` is configured, it acts as an **allow-list filter** (current behavior preserved). When `delegates_to` is empty/absent, the agent can delegate to **any other enabled agent** in the workspace.

### Behavior Matrix

| `delegates_to` in AGENT.md | Tool available? | Can delegate to |
|-----------------------------|-----------------|-----------------|
| Not specified (empty list)  | Yes             | Any enabled agent (except self) |
| Explicit list               | Yes             | Only listed agents |
| Single-agent workspace      | No              | N/A (no peers) |

## Scope

**In scope:**
- Register `delegate_to_agent` for all agents when workspace has 2+ agents
- Modify permission check: empty `delegates_to` = delegate to any enabled agent (except self)
- Add self-delegation guard (agent cannot delegate to itself)
- Update example project to demonstrate auto-delegation (agent without explicit `delegates_to`)
- Update documentation

**Out of scope:**
- Changing the delegation tool name, parameters, or return format
- Changing execution lineage tracking (already works)
- Changing `max_delegation_depth` guardrail (already works)
- Adding a `delegation: false` opt-out flag (can be a follow-up if needed)

## Prerequisites

None. This builds on the existing delegation infrastructure.

## Architecture / Design

### Current Flow (gateway.py lines 518-578)

1. After workspace loads, collect agents where `a.delegates_to` is non-empty
2. If any found, register `delegate_to_agent` as a `CodeTool` with `allowed_agents=delegation_agents`
3. In `run_delegation()`, check `agent_id not in delegates_to` from `ToolContext`

### New Flow

1. After workspace loads, check if workspace has 2+ agents
2. If yes, register `delegate_to_agent` as a `CodeTool` with `allowed_agents=None` (all agents)
3. In `run_delegation()`, change permission logic:
   - If `delegates_to` is non-empty: current behavior (allow-list check)
   - If `delegates_to` is empty: allow any enabled agent except the caller itself
   - Always block self-delegation regardless of config

### Key Change: Permission Check in `run_delegation()`

Current (`src/agent_gateway/engine/delegation.py` line 33):
```python
if agent_id not in delegates_to:
    return f"Error: Agent '{caller_agent_id}' is not allowed to delegate to '{agent_id}'. ..."
```

New:
```python
# Block self-delegation
if agent_id == caller_agent_id:
    return f"Error: Agent '{caller_agent_id}' cannot delegate to itself."

# Block delegation to disabled agents
if not gateway.is_agent_enabled(agent_id):
    return f"Error: Agent '{agent_id}' is currently disabled."

# If delegates_to is configured (non-empty list), enforce allow-list
if delegates_to is not None and len(delegates_to) > 0 and agent_id not in delegates_to:
    return (
        f"Error: Agent '{caller_agent_id}' is not allowed to delegate to '{agent_id}'. "
        f"Allowed targets: {delegates_to}"
    )

# If delegates_to is empty/None, any enabled agent is allowed
```

**Note**: Use explicit `delegates_to is not None and len(delegates_to) > 0` rather than just `if delegates_to:` to make the truthiness check clear and avoid fragile implicit behavior.

### Key Change: Tool Registration in `gateway.py`

Current (line 519):
```python
delegation_agents = [aid for aid, a in workspace.agents.items() if a.delegates_to]
if delegation_agents:
    ...
    delegation_tool = CodeTool(..., allowed_agents=delegation_agents)
```

New:
```python
if len(workspace.agents) >= 2:
    ...
    delegation_tool = CodeTool(..., allowed_agents=None)  # available to all agents
```

### Disabled Agent Guard

**Important**: `gateway.invoke()` does NOT check `agent.enabled` — that check only exists in the HTTP route handlers (`api/routes/invoke.py`, `api/routes/chat.py`). This means `run_delegation()` must explicitly guard against delegation to disabled agents.

Add existence and enabled checks in `run_delegation()` before calling `gateway.invoke()`:
```python
# Check agent exists
if gateway.agents.get(agent_id) is None:
    return f"Error: Agent '{agent_id}' does not exist. Available agents: {list(gateway.agents.keys())}"

# Check agent is enabled
if not gateway.is_agent_enabled(agent_id):
    return f"Error: Agent '{agent_id}' is currently disabled."
```
`gateway.is_agent_enabled()` already exists (line 253). The existence check must come first to avoid a misleading "disabled" message for non-existent agents.

## Implementation Steps

### Step 1: Update `run_delegation()` permission logic

**File:** `src/agent_gateway/engine/delegation.py`

1. Add self-delegation check before the allow-list check
2. Add agent existence check (`gateway.agents.get(agent_id) is None`) with error listing available agents
3. Add disabled-agent check (`not gateway.is_agent_enabled(agent_id)`)
4. Change the allow-list check to only apply when `delegates_to is not None and len(delegates_to) > 0`
5. Keep max-depth check unchanged

### Step 2: Update tool registration in `gateway.py`

**File:** `src/agent_gateway/gateway.py` (around line 518)

1. Change the condition from "any agent has delegates_to" to "workspace has 2+ agents"
2. Set `allowed_agents=None` on the `CodeTool` (available to all agents)
3. Update the log message to reflect that delegation is available to all agents
4. **Agent discoverability**: Populate the `agent_id` parameter's `description` field with the list of available agent IDs at registration time, so the LLM knows which agents it can delegate to without guessing. E.g.: `"The ID of the agent to delegate to. Available agents: assistant, researcher, email-drafter"`

### Step 3: Verify executor and streaming tool injection

**File:** `src/agent_gateway/engine/executor.py` (around line 175)
**File:** `src/agent_gateway/engine/streaming.py` (around lines 131, 314)

The executor already has logic at lines 176-179 that injects code tools permitted for the agent but not surfaced via skills. With `allowed_agents=None`, this will naturally include `delegate_to_agent` for all agents. **Verify that `streaming.py` has identical tool-injection and permission logic** — both paths must behave consistently. If they diverge, update `streaming.py` to match. No change expected, but must be explicitly confirmed.

### Step 4: Pass `delegates_to` correctly for unrestricted agents

**File:** `src/agent_gateway/gateway.py` (around line 2455)

Current:
```python
delegates_to=agent.delegates_to if agent.delegates_to else None,
```

This passes `None` when `delegates_to` is empty, which becomes `[]` in `ToolContext` via the default factory. The empty list correctly signals "unrestricted" in the new permission logic. **No change needed.** Note: verify under mypy that passing `delegates_to=None` does not violate the type annotation if the field is `list[str]` (not `list[str] | None`). If so, pass `agent.delegates_to` directly instead of the conditional.

### Step 5: Add delegation tool registration to `reload()`

**File:** `src/agent_gateway/gateway.py` — `reload()` method (around line 1901)

The `reload()` method re-registers memory tools but has **no delegation tool registration**. After a hot-reload, the delegation tool silently disappears from all agents. Add a delegation registration block inside `reload()` (after the memory tools block, before the atomic snapshot swap) that mirrors the `_startup` logic:

```python
if len(new_workspace.agents) >= 2:
    # Register delegate_to_agent with dynamic description listing available agents
    agent_ids = [aid for aid in new_workspace.agents]
    # ... same CodeTool construction as in _startup ...
    new_registry.register(delegation_tool)
```

This ensures the tool survives workspace reloads. The agent_id description is also refreshed with the current agent list on reload.

### Step 6: Update tests

**File:** `tests/test_integration/test_delegation.py` (or create if not exists)

Check what delegation tests exist:

New/updated tests:
1. **test_delegation_available_to_all_agents**: Verify that in a multi-agent workspace, all agents have `delegate_to_agent` in their tool list
2. **test_delegation_self_delegation_blocked**: Verify that an agent cannot delegate to itself
3. **test_delegation_unrestricted_when_no_delegates_to**: Verify that an agent without `delegates_to` can delegate to any other enabled agent
4. **test_delegation_restricted_when_delegates_to_set**: Verify that an agent with `delegates_to` can only delegate to listed agents (existing behavior preserved)
5. **test_delegation_single_agent_workspace_no_tool**: Verify that in a single-agent workspace, `delegate_to_agent` is not registered
6. **test_delegation_to_disabled_agent_blocked**: Verify that delegating to a disabled agent returns an error string rather than invoking it
7. **test_delegation_to_nonexistent_agent_returns_error**: Verify that delegating to a non-existent agent returns an error listing available agents
8. **test_delegation_tool_survives_reload**: Start a multi-agent gateway, reload the workspace, assert `delegate_to_agent` is present in all agent tool lists post-reload

### Step 7: Update example project

**File:** `examples/test-project/workspace/agents/researcher/AGENT.md`

Add a demonstration that the researcher agent (which does NOT have `delegates_to` configured) can now delegate back to the coordinator or email-drafter if needed. Alternatively, add a brief comment in the coordinator's AGENT.md noting that `delegates_to` is now optional (acts as a filter).

More impactful: update the example project's `README` or `app.py` to show that delegation works without explicit `delegates_to`.

### Step 7: Update documentation

**File:** `docs/guides/delegation.md`

1. Update the "Configuration" section to explain that `delegate_to_agent` is now built-in for all agents
2. Clarify that `delegates_to` is optional and acts as an allow-list filter
3. Add a note about self-delegation being blocked
4. Update the "Permission Model" section

**File:** `docs/guides/agents.md` - Update any reference to `delegates_to` being required.

**File:** `docs/api-reference/configuration.md` - Update `delegates_to` description.

**File:** `docs/llms.txt` - Sync changes.

## Testing Strategy

### Unit Tests

- `test_run_delegation_self_delegation_blocked` - Call `run_delegation` where `caller_agent_id == agent_id`, assert error string returned
- `test_run_delegation_unrestricted_allows_any` - Call `run_delegation` with empty `delegates_to`, assert delegation proceeds
- `test_run_delegation_restricted_blocks_unlisted` - Call with `delegates_to=["a"]` and `agent_id="b"`, assert error (existing)
- `test_run_delegation_disabled_agent_blocked` - Call `run_delegation` targeting a disabled agent, assert error string returned

### Integration Tests

- `test_tool_registered_for_all_agents_multi_workspace` - Start gateway with 2+ agents, verify `delegate_to_agent` in all agent tool lists
- `test_tool_not_registered_single_agent_workspace` - Start gateway with 1 agent, verify no delegation tool
- `test_existing_delegates_to_behavior_preserved` - Agent with explicit `delegates_to` can only delegate to listed targets

### Markers

- Use `@pytest.mark.asyncio` (auto mode, so just `async def` suffices)
- No e2e or postgres markers needed; these are unit/integration tests

## Example Project Updates

In `examples/test-project/`:
- Optionally add a new agent (e.g., `summarizer`) without `delegates_to` to show it can still delegate
- Or simply remove `delegates_to` from the coordinator's AGENT.md to demonstrate the new default behavior (delegate to any agent)
- Update `app.py` comments if relevant

## Documentation Updates

| File | Change |
|------|--------|
| `docs/guides/delegation.md` | Rewrite "Configuration" section; `delegates_to` is now optional |
| `docs/guides/agents.md` | Update `delegates_to` frontmatter docs |
| `docs/api-reference/configuration.md` | Update `delegates_to` field description |
| `docs/llms.txt` | Sync delegation changes |

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Agents delegate unexpectedly without explicit config | Medium | Low | `max_delegation_depth` guardrail already prevents runaway chains; self-delegation blocked |
| Breaking change for users who relied on "no delegates_to = no delegation" | Low | Medium | **This is a behavioral change**: agents that previously had no delegation capability will now have it. Document prominently in changelog and migration notes. The tool being available doesn't force the LLM to use it, but it may use it if the task warrants delegation. A `delegation: false` opt-out flag can be added as a follow-up if needed. |
| Delegation to disabled agents | Medium | High | Explicitly guarded in `run_delegation()` via `gateway.is_agent_enabled()` |
| Circular delegation (A->B->A->B...) | Medium | Medium | Already handled by `max_delegation_depth` guardrail (default 3) |

## Verification Checklist

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest -m "not e2e" -x -q
```

- [ ] `delegate_to_agent` registered for all agents in multi-agent workspaces
- [ ] Self-delegation returns error message
- [ ] Empty `delegates_to` allows delegation to any enabled agent
- [ ] Explicit `delegates_to` still restricts targets (backward compatible)
- [ ] Single-agent workspace does not register delegation tool
- [ ] Example project updated
- [ ] Documentation updated
- [ ] All linting/typing/tests pass
