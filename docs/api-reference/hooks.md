# Lifecycle Hooks

Hooks let you observe and react to gateway events without modifying execution logic. They are useful for logging, metrics, audit trails, alerting, and integration with external systems.

---

## Registering Hooks

Use the `@gw.on(event)` decorator. Hook functions must be `async`.

```python
@gw.on("agent.invoke.before")
async def on_before_invoke(agent_id: str, message: str, execution_id: str, **kw):
    print(f"[{execution_id}] Invoking agent '{agent_id}'")
```

Multiple hooks can be registered for the same event. They are called in registration order.

Hooks can also be registered by calling `gw._hooks.register(event, fn)` directly, though the decorator is preferred.

---

## Error Handling

Hook failures are **logged as warnings and never propagate**. A broken hook cannot crash an execution or the gateway itself. If a hook raises an exception, the exception is logged at `WARNING` level and the next registered hook for that event continues normally.

---

## Events

### `agent.invoke.before`

Fired immediately before an agent execution begins.

| Keyword argument | Type | Description |
|-----------------|------|-------------|
| `agent_id` | `str` | The agent being invoked. |
| `message` | `str` | The user message. |
| `execution_id` | `str` | Unique ID for this execution. |

```python
@gw.on("agent.invoke.before")
async def before_invoke(agent_id: str, message: str, execution_id: str, **kw):
    await metrics.increment("agent.invocations", tags={"agent": agent_id})
```

---

### `agent.invoke.after`

Fired after an agent execution completes (whether successful, failed, or cancelled).

| Keyword argument | Type | Description |
|-----------------|------|-------------|
| `agent_id` | `str` | The agent that was invoked. |
| `message` | `str` | The original user message. |
| `execution_id` | `str` | Unique ID for this execution. |
| `result` | `ExecutionResult` | The execution result, including `.raw_text`, `.usage`, `.stop_reason`. |

```python
@gw.on("agent.invoke.after")
async def after_invoke(agent_id: str, execution_id: str, result, **kw):
    if result.usage:
        await metrics.record(
            "agent.tokens",
            result.usage.total_tokens,
            tags={"agent": agent_id},
        )
```

---

### `tool.execute.before`

Fired before a tool call is dispatched to the tool executor.

| Keyword argument | Type | Description |
|-----------------|------|-------------|
| `tool_name` | `str` | The tool being called. |
| `agent_id` | `str` | The agent that requested the tool call. |
| `execution_id` | `str` | The parent execution ID. |

```python
@gw.on("tool.execute.before")
async def before_tool(tool_name: str, agent_id: str, execution_id: str, **kw):
    logger.debug("Tool %s called by %s (exec %s)", tool_name, agent_id, execution_id)
```

---

### `tool.execute.after`

Fired after a tool call returns (or raises).

| Keyword argument | Type | Description |
|-----------------|------|-------------|
| `tool_name` | `str` | The tool that was called. |
| `agent_id` | `str` | The agent that requested the tool call. |
| `execution_id` | `str` | The parent execution ID. |

---

### `llm.call.before`

Fired immediately before each LLM API call.

| Keyword argument | Type | Description |
|-----------------|------|-------------|
| `agent_id` | `str` | The agent driving this LLM call. |
| `execution_id` | `str` | The parent execution ID. |

---

### `llm.call.after`

Fired after each LLM API call completes.

| Keyword argument | Type | Description |
|-----------------|------|-------------|
| `agent_id` | `str` | The agent driving this LLM call. |
| `execution_id` | `str` | The parent execution ID. |

---

### `gateway.startup`

Fired once, at the end of Gateway startup, after all components are initialized.

No keyword arguments.

```python
@gw.on("gateway.startup")
async def on_startup(**kw):
    logger.info("Gateway is up with %d agents", len(gw.agents))
```

---

### `gateway.shutdown`

Fired once, at the beginning of Gateway shutdown, before any cleanup.

No keyword arguments.

```python
@gw.on("gateway.shutdown")
async def on_shutdown(**kw):
    await external_client.close()
```

---

## Complete Example

```python
import logging
from agent_gateway import Gateway

logger = logging.getLogger(__name__)

gw = Gateway(workspace="./workspace")


@gw.on("gateway.startup")
async def on_startup(**kw):
    logger.info("Gateway started. Agents: %s", list(gw.agents.keys()))


@gw.on("gateway.shutdown")
async def on_shutdown(**kw):
    logger.info("Gateway shutting down")


@gw.on("agent.invoke.before")
async def on_invoke_before(agent_id: str, message: str, execution_id: str, **kw):
    logger.info("[%s] → %s: %.80s", execution_id, agent_id, message)


@gw.on("agent.invoke.after")
async def on_invoke_after(agent_id: str, execution_id: str, result, **kw):
    tokens = result.usage.total_tokens if result.usage else "unknown"
    logger.info("[%s] ← %s: %s tokens, stop=%s", execution_id, agent_id, tokens, result.stop_reason)


@gw.on("tool.execute.before")
async def on_tool(tool_name: str, agent_id: str, **kw):
    logger.debug("Tool '%s' called by '%s'", tool_name, agent_id)


if __name__ == "__main__":
    gw.run()
```

---

## Valid Event Names

Attempting to register a hook for an unknown event name raises `ValueError` immediately.

```
agent.invoke.before
agent.invoke.after
tool.execute.before
tool.execute.after
llm.call.before
llm.call.after
gateway.startup
gateway.shutdown
```
