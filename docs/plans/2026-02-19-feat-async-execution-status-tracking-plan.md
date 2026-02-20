---
title: "Async execution status tracking (Celery-like task monitoring)"
type: feat
status: active
date: 2026-02-19
---

# Async Execution Status Tracking

## Overview

Improve the async execution experience so developers can easily track, poll, and inspect queued/running agent executions — similar to how Celery exposes `AsyncResult` with status, result, and metadata.

## Problem Statement

The core infrastructure exists (202 responses with `poll_url`, `GET /v1/executions/{id}`, worker status updates), but the developer experience has gaps:

1. **No programmatic async invoke** — `gw.invoke()` is sync-only; async requires HTTP
2. **No CLI command** to check execution status or poll until completion
3. **No global execution listing** — `GET /v1/executions` requires `agent_id` filter
4. **No execution steps/progress** — the `execution_steps` table exists but is never populated
5. **No status filtering** — can't query "show me all running executions"

## Proposed Solution

Add the missing layers that turn the existing infrastructure into a complete async task monitoring system.

## Acceptance Criteria

### Programmatic API (`gateway.py`)

- [ ] `gw.invoke_async(agent_id, message, ...) -> str` returns `execution_id` immediately
- [ ] `gw.get_execution(execution_id) -> ExecutionRecord | None` retrieves execution status
- [ ] `gw.list_executions(agent_id=None, status=None, limit=50) -> list[ExecutionRecord]` lists executions with optional filters

### CLI

- [ ] `agent-gateway executions <execution_id>` shows execution status, result, and timing
- [ ] `agent-gateway executions --list` lists recent executions
- [ ] `agent-gateway executions <execution_id> --wait` polls until terminal status, then prints result
- [ ] `agent-gateway invoke <agent_id> --async` invokes asynchronously and prints execution_id + poll URL

### HTTP API Improvements

- [ ] `GET /v1/executions` works without `agent_id` filter (lists all, paginated)
- [ ] `GET /v1/executions?status=running` filters by status
- [ ] `GET /v1/executions?status=queued,running` supports multiple status values

### Execution Steps / Progress

- [ ] Worker records execution steps as the agent progresses (LLM call started, tool invoked, tool completed)
- [ ] `GET /v1/executions/{id}` response includes `steps` array when available
- [ ] Steps include timestamp, type (llm_call | tool_start | tool_complete), and metadata

## Technical Approach

### 1. Programmatic API — `gateway.py`

```python
# examples/test-project/app.py
async def main():
    async with Gateway(workspace="./workspace") as gw:
        # Fire and forget
        exec_id = await gw.invoke_async("data-processor", "Analyze Q4 data")
        print(f"Queued: {exec_id}")

        # Poll
        record = await gw.get_execution(exec_id)
        print(f"Status: {record.status}")

        # List running
        running = await gw.list_executions(status="running")
```

**`invoke_async`** reuses the same logic as the HTTP 202 path in `api/routes/invoke.py`:
- Create `ExecutionRecord` with status=QUEUED
- Enqueue `ExecutionJob` to queue backend (or background task if NullQueue)
- Return `execution_id`

**`get_execution`** delegates to `self._execution_repo.get(execution_id)`.

**`list_executions`** requires adding a `list_all` method to `ExecutionRepository` (currently there's a `# TODO: add a list_all method` at `api/routes/executions.py:84`).

### 2. ExecutionRepository — New Methods

Add to `persistence/protocols.py`:

```python
class ExecutionRepository(Protocol):
    # ... existing methods ...
    async def list_all(
        self,
        status: str | list[str] | None = None,
        limit: int = 50,
    ) -> list[ExecutionRecord]: ...
```

Implement in `persistence/backends/sql/repository.py`:

```python
async def list_all(self, status=None, limit=50):
    async with self._session_factory() as session:
        query = select(ExecutionRecord).order_by(
            ExecutionRecord.created_at.desc()
        ).limit(limit)
        if status:
            if isinstance(status, list):
                query = query.where(ExecutionRecord.status.in_(status))
            else:
                query = query.where(ExecutionRecord.status == status)
        result = await session.execute(query)
        return list(result.scalars().all())
```

Also add to `NullExecutionRepository` (returns empty list).

### 3. HTTP API — Remove `agent_id` Requirement

Update `GET /v1/executions` in `api/routes/executions.py`:

```python
@router.get("/executions")
async def list_executions(
    request: Request,
    agent_id: str | None = Query(None),
    status: str | None = Query(None, description="Filter by status (comma-separated)"),
    limit: int = Query(50, ge=1, le=500),
) -> list[ExecutionResponse]:
    gw: Gateway = request.app
    if agent_id:
        records = await gw._execution_repo.list_by_agent(agent_id, limit=limit)
    else:
        status_filter = status.split(",") if status else None
        records = await gw._execution_repo.list_all(status=status_filter, limit=limit)
    return [_record_to_response(r) for r in records]
```

### 4. CLI — `executions` Command

New file: `src/agent_gateway/cli/executions.py`

```
$ agent-gateway executions abc-123
Execution: abc-123
Agent:     data-processor
Status:    completed
Started:   2026-02-19T05:52:30Z
Completed: 2026-02-19T05:52:36Z
Duration:  6.7s
Result:    Processed data for query 'Analyze sales'...
Tokens:    416 in / 34 out ($0.000055)

$ agent-gateway executions --list
ID          AGENT            STATUS      AGE
abc-123     data-processor   completed   2m ago
def-456     assistant        running     30s ago

$ agent-gateway executions abc-123 --wait
Waiting for abc-123... queued → running → completed (6.7s)
Result: Processed data for query 'Analyze sales'...
```

### 5. CLI — Async Invoke

Update `src/agent_gateway/cli/invoke.py` to support `--async` flag:

```
$ agent-gateway invoke data-processor "Analyze Q4 data" --async
Queued: abc-123
Poll:   GET /v1/executions/abc-123

$ agent-gateway invoke data-processor "Analyze Q4 data" --async --wait
Queued: abc-123
Waiting... queued → running → completed (6.7s)
Result: Processed data for query 'Analyze sales'...
```

### 6. Execution Steps (Progress Tracking)

The `execution_steps` table and `ExecutionStep` dataclass already exist in the schema:

```python
# persistence/domain.py
@dataclass
class ExecutionStep:
    id: str
    execution_id: str
    step_type: str  # "llm_call" | "tool_start" | "tool_complete"
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime | None = None
```

**Wire steps into the engine/worker:**

- In `ExecutionEngine.execute()` or via hooks: record steps when the LLM is called and when tools start/complete
- Use the existing `execution_repo.add_step()` method
- Include steps in the `GET /v1/executions/{id}` response

This gives progress visibility:

```json
{
  "execution_id": "abc-123",
  "status": "running",
  "steps": [
    {"type": "llm_call", "timestamp": "...", "data": {"model": "gemini-2.0-flash"}},
    {"type": "tool_start", "timestamp": "...", "data": {"tool": "process-data"}},
    {"type": "tool_complete", "timestamp": "...", "data": {"tool": "process-data", "duration_ms": 5000}}
  ]
}
```

## Implementation Phases

### Phase 1: Core API (Programmatic + HTTP)

- [ ] Add `list_all()` to `ExecutionRepository` protocol and SQL implementation
- [ ] Add `NullExecutionRepository.list_all()` (returns `[]`)
- [ ] Add `gw.invoke_async()` to `gateway.py`
- [ ] Add `gw.get_execution()` to `gateway.py`
- [ ] Add `gw.list_executions()` to `gateway.py`
- [ ] Update `GET /v1/executions` to work without `agent_id`, add `status` filter
- [ ] Tests for all new methods

### Phase 2: CLI Commands

- [ ] Add `executions` CLI command (get, list, wait)
- [ ] Add `--async` and `--wait` flags to `invoke` CLI command
- [ ] Tests for CLI commands

### Phase 3: Execution Steps

- [ ] Wire step recording into engine hooks (llm_call, tool_start, tool_complete)
- [ ] Include steps in execution API response
- [ ] Add `steps` to `ExecutionResponse` model
- [ ] Tests for step tracking

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `src/agent_gateway/gateway.py` | Edit | Add `invoke_async()`, `get_execution()`, `list_executions()` |
| `src/agent_gateway/persistence/protocols.py` | Edit | Add `list_all()` to `ExecutionRepository` |
| `src/agent_gateway/persistence/backends/sql/repository.py` | Edit | Implement `list_all()` with status filter |
| `src/agent_gateway/persistence/null.py` | Edit | Add `list_all()` stub |
| `src/agent_gateway/api/routes/executions.py` | Edit | Remove `agent_id` requirement, add `status` filter |
| `src/agent_gateway/api/models.py` | Edit | Add `steps` to `ExecutionResponse` |
| `src/agent_gateway/cli/executions.py` | **Create** | New CLI command for execution status |
| `src/agent_gateway/cli/invoke.py` | Edit | Add `--async` and `--wait` flags |
| `src/agent_gateway/cli/__init__.py` | Edit | Register new command |
| `tests/test_persistence/` | Edit | Tests for `list_all()` |
| `tests/test_integration/` | Edit | Tests for programmatic API |
| `tests/test_cli/` | Edit | Tests for CLI commands |

## References

- Existing execution endpoint: `src/agent_gateway/api/routes/executions.py:50-87`
- Invoke async logic: `src/agent_gateway/api/routes/invoke.py:150-183`
- Worker status updates: `src/agent_gateway/queue/worker.py:181-245`
- ExecutionRepository protocol: `src/agent_gateway/persistence/protocols.py:10-29`
- ExecutionRecord domain model: `src/agent_gateway/persistence/domain.py:14-30`
- ExecutionStep domain model: `src/agent_gateway/persistence/domain.py:33-42`
- list_all TODO: `src/agent_gateway/api/routes/executions.py:84`
- CLI entry point: `src/agent_gateway/cli/__init__.py`
