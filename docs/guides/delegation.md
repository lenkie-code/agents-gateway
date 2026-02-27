# Agent-to-Agent Delegation

Agent delegation allows one agent to hand off tasks to other agents, enabling multi-agent workflows with full execution lineage tracking.

## Overview

A **coordinator** agent can delegate subtasks to **specialist** agents using the built-in `delegate_to_agent` tool. Each delegation creates a child execution linked to the parent, forming a workflow tree with cost rollup.

## Configuration

### Agent Setup

The `delegate_to_agent` tool is **automatically available to all agents** in any workspace with two or more agents. No configuration is required — agents can discover and delegate to any other enabled agent.

To **restrict** which agents a particular agent can delegate to, add `delegates_to` to its `AGENT.md` frontmatter:

```yaml
---
description: "Project coordinator"
delegates_to:
  - researcher
  - writer
  - reviewer
---
```

When `delegates_to` is specified, it acts as an **allow-list filter** — the agent can only delegate to the listed targets. When omitted, the agent can delegate to any other enabled agent in the workspace.

!!! note
    In a single-agent workspace, the delegation tool is not registered since there are no peers to delegate to.

### Guardrails

Control maximum delegation depth in `gateway.yaml`:

```yaml
guardrails:
  max_delegation_depth: 3  # default
```

This prevents infinite delegation loops. Each delegation increments the depth counter; when it reaches the maximum, further delegations are rejected.

## How It Works

1. The coordinator agent receives a request
2. It calls `delegate_to_agent` with a target agent ID and message
3. The gateway creates a child execution linked to the parent
4. The target agent processes the request and returns a result
5. The coordinator receives the result as a tool response
6. The coordinator can delegate to additional agents or produce a final response

### Delegation Tool Schema

The `delegate_to_agent` tool accepts:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | Yes | ID of the target agent |
| `message` | string | Yes | Task description for the target agent |
| `input` | object | No | Structured input for the target agent |

### Permission Model

- **No `delegates_to`** (default): The agent can delegate to any other enabled agent except itself
- **With `delegates_to`**: The agent can only delegate to the listed agents
- **Self-delegation** is always blocked — an agent cannot delegate to itself
- **Disabled agents** cannot be delegation targets — attempting to delegate to a disabled agent returns an error
- **Non-existent agents** return an error listing available agents
- The delegation depth is enforced globally via `max_delegation_depth`

## Execution Lineage

Every execution in a delegation chain tracks:

- **`parent_execution_id`**: The direct parent that delegated to this execution
- **`root_execution_id`**: The root of the entire workflow tree
- **`delegation_depth`**: How deep in the delegation tree this execution is

### API Endpoints

**Get workflow tree:**
```
GET /v1/executions/{execution_id}/workflow
```
Returns all executions in the delegation tree, ordered by depth and creation time.

**Filter by root execution:**
```
GET /v1/executions?root_execution_id={id}
```
Returns all executions belonging to a specific workflow tree.

### Dashboard

The execution detail page in the dashboard shows:
- A link to the parent execution (if delegated)
- A list of child executions (if this execution delegated to others)
- Total workflow cost rollup for root executions
- A "Workflow" badge for executions that are part of a delegation chain

## Example

### Coordinator with Allow-List (`workspace/agents/coordinator/AGENT.md`)

```yaml
---
description: "Coordinator that orchestrates research and writing"
delegates_to:
  - researcher
  - writer
---
```

This coordinator can **only** delegate to `researcher` and `writer`.

### Specialist with Auto-Delegation (`workspace/agents/researcher/AGENT.md`)

```yaml
---
description: "Research specialist"
---
```

This researcher has **no** `delegates_to` — it can delegate to any other enabled agent in the workspace (e.g., hand off email drafting to an `email-drafter` agent).

### Programmatic Usage

```python
from agent_gateway import Gateway

async with Gateway(workspace="./workspace") as gw:
    result = await gw.invoke("coordinator", "Create a report on AI trends")
    # The coordinator will delegate to researcher and writer automatically
```

## Cost Tracking

Delegation creates a tree of executions. The total workflow cost can be queried:

- **Dashboard**: Root executions show a "Total Workflow Cost" in the delegation panel
- **API**: Use `GET /v1/executions/{id}/workflow` and sum the usage across all executions
