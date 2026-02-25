---
title: "Streaming Engine Tests"
status: completed
priority: P2
category: Testing
date: 2026-02-22
---

# Streaming Engine Tests

## Summary

Create comprehensive tests for `/Users/vince/Src/HonesDev/agent-gateway/src/agent_gateway/engine/streaming.py` covering the `stream_chat_execution` async generator and its helper functions (`_sse_event`, `_truncate_result`, `_serialize_tool_output`). The streaming module is currently untested.

## Scope

**In scope:**
- Unit tests for `_sse_event`, `_truncate_result`, `_serialize_tool_output`
- Integration tests for `stream_chat_execution` covering all event types and control flow paths

**Out of scope:**
- HTTP-level SSE testing (belongs in API route tests)
- Changes to production code

## Prerequisites

The existing `MockLLMClient` in `/Users/vince/Src/HonesDev/agent-gateway/tests/test_engine/conftest.py` does **not** have a `stream_completion` method. A streaming-capable mock must be added.

## Architecture

`stream_chat_execution` is an async generator that accepts a `Gateway` instance and yields SSE-formatted strings. Testing it requires mocking:

1. **`gw._snapshot`** — needs `.engine` (with `._llm`, `._registry`) and `.workspace`
2. **`gw._execution_repo`** — use `NullExecutionRepository` from `/Users/vince/Src/HonesDev/agent-gateway/src/agent_gateway/persistence/null.py` (all no-ops)
3. **`gw._config`** — use default `GatewayConfig()`
4. **`gw._execution_semaphore`** — a real `asyncio.Semaphore`
5. **`session`** — a real `ChatSession` from `/Users/vince/Src/HonesDev/agent-gateway/src/agent_gateway/chat/session.py`
6. **`handle`** — a real `ExecutionHandle`

The mock LLM's `stream_completion` must be an async generator yielding `{"type": "token"|"tool_call"|"usage", ...}` dicts matching the contract at `/Users/vince/Src/HonesDev/agent-gateway/src/agent_gateway/engine/llm.py:158-172`.

## Implementation Steps

### Step 1: Extend `MockLLMClient` in conftest

**File:** `/Users/vince/Src/HonesDev/agent-gateway/tests/test_engine/conftest.py`

Add `from collections.abc import AsyncIterator` and `import json` to imports.

Add a `stream_completion` async generator method to `MockLLMClient` (after the existing `completion` method, around line 124):

```python
async def stream_completion(
    self,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield pre-configured streaming chunks derived from LLMResponse."""
    self.calls.append({
        "messages": messages,
        "tools": tools,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    })
    if self._call_count >= len(self._responses):
        raise RuntimeError("No more mock responses configured")
    response = self._responses[self._call_count]
    self._call_count += 1
    # Convert LLMResponse into streaming chunks
    if response.text:
        # Yield text as individual character tokens to simulate streaming
        for char in response.text:
            yield {"type": "token", "content": char}
    for tc in response.tool_calls:
        yield {
            "type": "tool_call",
            "name": tc.name,
            "arguments": json.dumps(tc.arguments),
            "call_id": tc.call_id,
        }
    yield {
        "type": "usage",
        "model": response.model,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "cost": response.cost,
    }
```

This converts existing `LLMResponse` objects into streaming chunks, so all existing `make_llm_response` helpers work for streaming tests too.

### Step 2: Add `make_mock_gateway` helper to conftest

**File:** `/Users/vince/Src/HonesDev/agent-gateway/tests/test_engine/conftest.py`

Add at the end of the file. This builds a minimal mock with just the attributes `stream_chat_execution` reads from the gateway:

```python
from unittest.mock import MagicMock
from agent_gateway.persistence.null import NullExecutionRepository

def make_mock_gateway(
    engine: ExecutionEngine,
    workspace: WorkspaceState,
    config: GatewayConfig | None = None,
    semaphore_value: int = 5,
) -> MagicMock:
    """Create a mock Gateway with attributes needed by stream_chat_execution."""
    gw = MagicMock()
    snapshot = MagicMock()
    snapshot.engine = engine
    snapshot.workspace = workspace
    gw._snapshot = snapshot
    gw._execution_repo = NullExecutionRepository()
    gw._config = config or GatewayConfig()
    gw._execution_semaphore = asyncio.Semaphore(semaphore_value)
    return gw
```

Also add `import asyncio` to the conftest imports.

### Step 3: Create test file

**File:** `/Users/vince/Src/HonesDev/agent-gateway/tests/test_engine/test_streaming.py`

#### Imports

```python
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from agent_gateway.chat.session import ChatSession
from agent_gateway.config import GatewayConfig, GuardrailsConfig
from agent_gateway.engine.models import ExecutionHandle, ExecutionOptions
from agent_gateway.engine.streaming import (
    MAX_RESULT_SIZE,
    _serialize_tool_output,
    _sse_event,
    _truncate_result,
    stream_chat_execution,
)
from tests.test_engine.conftest import (
    make_agent,
    make_engine,
    make_llm_response,
    make_mock_gateway,
    make_resolved_tool,
    make_skill,
    make_tool_call,
    make_workspace,
)
```

#### Helper function

```python
async def collect_events(sse_iter: AsyncIterator[str]) -> list[tuple[str, Any]]:
    """Drain an SSE async iterator, returning (event_type, parsed_data) tuples."""
    events: list[tuple[str, Any]] = []
    async for raw in sse_iter:
        lines = raw.strip().split("\n")
        event_type = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((event_type, data))
    return events
```

#### Helper to build common streaming test args

```python
def _make_stream_args(
    gw: Any,
    agent: Any | None = None,
    session: ChatSession | None = None,
    messages: list[dict[str, Any]] | None = None,
    exec_options: ExecutionOptions | None = None,
    execution_id: str = "exec_1",
    handle: ExecutionHandle | None = None,
) -> dict[str, Any]:
    """Build kwargs dict for stream_chat_execution."""
    _agent = agent or make_agent()
    return {
        "gw": gw,
        "agent": _agent,
        "session": session or ChatSession(session_id="sess_1", agent_id=_agent.id),
        "messages": messages or [{"role": "user", "content": "Hello"}],
        "exec_options": exec_options or ExecutionOptions(),
        "execution_id": execution_id,
        "handle": handle or ExecutionHandle(execution_id=execution_id),
    }
```

#### Test Classes

---

**Class `TestSseEvent`** — Unit tests for the `_sse_event` helper:

1. **`test_sse_event_format_dict`** — Pass `_sse_event("token", {"content": "hi"})`, assert output is exactly `'event: token\ndata: {"content": "hi"}\n\n'`.

2. **`test_sse_event_format_string`** — Pass `_sse_event("error", "raw string")`, assert data line is `data: raw string\n` (not double-JSON-encoded).

3. **`test_sse_event_special_characters`** — Pass dict with unicode and newlines in values. Assert the JSON in the data line is valid (parseable by `json.loads`).

---

**Class `TestTruncateResult`** — Unit tests for `_truncate_result`:

1. **`test_short_string_unchanged`** — String of length 100, returned as-is.

2. **`test_long_string_truncated`** — String of length `MAX_RESULT_SIZE + 100`. Assert result length is `MAX_RESULT_SIZE + len("\n[truncated: result exceeded 32KB limit]")`. Assert ends with the truncation suffix.

3. **`test_exact_limit_unchanged`** — String of exactly `MAX_RESULT_SIZE`, returned as-is.

---

**Class `TestSerializeToolOutput`** — Unit tests for `_serialize_tool_output`:

1. **`test_string_passthrough`** — `_serialize_tool_output("hello")` returns `"hello"`.

2. **`test_dict_to_json`** — `_serialize_tool_output({"key": "val"})` returns `json.dumps({"key": "val"})`.

3. **`test_non_serializable_to_str`** — Pass an object (e.g. `object()`). Assert result is `str(obj)`.

---

**Class `TestTokenEventEmission`** — Integration: streaming text responses.

1. **`test_text_tokens_emitted`**
   - Configure: `make_engine(responses=[make_llm_response(text="Hi")])` -> engine, mock_llm, registry
   - Build gateway mock via `make_mock_gateway(engine, workspace)`
   - Call `collect_events(stream_chat_execution(**_make_stream_args(gw)))`
   - Assert first event is `("session", {"session_id": ..., "execution_id": ...})`
   - Assert `token` events present, concatenated content equals `"Hi"`
   - Assert last event is `("done", {...})` with `data["status"] == "completed"`

2. **`test_sse_raw_format_matches_spec`**
   - Same setup as above, but iterate raw strings instead of using `collect_events`
   - Assert each raw string matches pattern: starts with `event: `, contains `\ndata: `, ends with `\n\n`

---

**Class `TestToolCallAndResultEvents`**:

1. **`test_tool_call_and_result_events`**
   - Setup: echo tool, first response has tool_call, second response has text "Done"
   - Workspace with skill mapping
   - Assert events sequence includes: `session`, `tool_call` (with name, arguments, call_id), `tool_result` (with output), token events for "Done", `done`

2. **`test_unknown_tool_returns_error_result`**
   - First response calls tool "nonexistent", second response has text
   - Assert `tool_result` event has `output.error` containing `"Unknown tool"`

3. **`test_tool_permission_denied`**
   - Create tool with `allowed_agents=["other-agent"]`, agent is "test-agent"
   - Assert `tool_result` has error about not permitted

---

**Class `TestUsageEvent`**:

1. **`test_done_event_contains_usage`**
   - Simple text response. Assert `done` event data has `usage` dict with keys: `input_tokens`, `output_tokens`, `cost_usd`, `llm_calls`, `tool_calls`, `duration_ms`, `models_used`.

2. **`test_usage_accumulates_across_iterations`**
   - Two LLM calls (tool call loop). Assert `done.usage.llm_calls == 2`, `input_tokens` and `output_tokens` are sums of both responses.

---

**Class `TestErrorEvent`**:

1. **`test_llm_failure_emits_error_event`**
   - Subclass or patch `MockLLMClient.stream_completion` to raise `RuntimeError`
   - Assert an `error` event with `{"message": "LLM call failed"}` appears
   - Assert `done` event has `status: "error"`

---

**Class `TestSessionLock`**:

1. **`test_session_lock_released_after_streaming`**
   - Create a `ChatSession`, run `stream_chat_execution` to completion (drain all events)
   - After completion, assert `session.lock.locked()` is `False` (can acquire without blocking)

2. **`test_session_lock_blocks_concurrent_access`**
   - Pre-acquire session lock in test code
   - Start `stream_chat_execution` as a task
   - Wait briefly (0.1s), assert no events produced yet (task is blocked on lock)
   - Release the lock, await the task, assert events produced normally

---

**Class `TestCancellation`**:

1. **`test_cancel_before_iteration`**
   - Create handle, call `handle.cancel()` before starting
   - Drain events. Assert `done` event has `status: "cancelled"`, no `token` events

2. **`test_cancel_between_tool_iterations`**
   - First response has tool_call. Patch the mock's `stream_completion` to call `handle.cancel()` after yielding from the first call (before the second call would start)
   - Assert `done` has `status: "cancelled"`

---

**Class `TestConcurrencySemaphore`**:

1. **`test_semaphore_limits_concurrent_streams`**
   - Create gateway with `semaphore_value=1`
   - Patch `stream_completion` to include an `asyncio.sleep(0.2)` to slow it down
   - Start two `stream_chat_execution` generators as tasks
   - Use `asyncio.wait` with `timeout=0.05` on the second task, assert it hasn't completed
   - Await both, assert both eventually produce `done` events

---

**Class `TestMaxToolCalls`**:

1. **`test_max_tool_calls_stops_iteration`**
   - Config: `GatewayConfig(guardrails=GuardrailsConfig(max_tool_calls=1))`
   - First response has 2 tool_calls. Only 1 should execute.
   - Assert `done` with `status: "max_tool_calls"`

---

**Class `TestMaxIterations`**:

1. **`test_max_iterations_stops_loop`**
   - Config: `GatewayConfig(guardrails=GuardrailsConfig(max_iterations=1))`
   - First response has a tool_call (requiring a second iteration)
   - Assert `done` with `status: "max_iterations"`

---

**Class `TestTimeout`**:

1. **`test_timeout_emits_error_and_done`**
   - `exec_options=ExecutionOptions(timeout_ms=1)`
   - Patch `stream_completion` to `asyncio.sleep(1.0)` before yielding
   - Assert `error` event with `"timed out"` message, `done` with `status: "timeout"`

---

**Class `TestEngineNotAvailable`**:

1. **`test_no_snapshot_yields_error`**
   - Set `gw._snapshot = None`
   - Assert single event: `("error", {"message": "Engine not available"})`

2. **`test_no_engine_yields_error`**
   - Set `gw._snapshot.engine = None`
   - Assert single event: `("error", {"message": "Engine not available"})`

## Testing Strategy

- All tests are unit or integration (no `@pytest.mark.e2e`)
- All async tests use `@pytest.mark.asyncio`
- Organized by feature/behavior in classes
- `collect_events` helper standardizes event parsing
- **Estimated test count: ~22 tests across 12 classes**

## Example Project & Documentation

Test-only change. No updates needed to `examples/test-project/` or `docs/`.

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| `stream_completion` mock interface mismatch | Exact signature copied from `llm.py:158` |
| Session lock timing test flakiness | Use deterministic asyncio patterns (pre-acquire lock, not timing-based) |
| `GuardrailsConfig` field names | Verified at `config.py:86-90`: `max_tool_calls`, `max_iterations`, `timeout_ms` |
| Importing private functions (`_sse_event`, etc.) | Acceptable for unit tests of module internals |

## Verification Checklist

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest tests/test_engine/test_streaming.py -x -v
uv run pytest -m "not e2e" -x -q
```
