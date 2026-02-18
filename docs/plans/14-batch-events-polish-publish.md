---
title: "Phase 3: Batch, Events, Rate Limiting, Polish & Publishing"
type: feat
status: pending
date: 2026-02-18
depends_on: [08, 09, 10, 11, 12, 13]
blocks: []
parent: 2026-02-18-feat-agent-gateway-framework-plan.md
---

# Phase 3: Batch, Events, Rate Limiting, Polish & Publishing

## Goal

Final polish: batch invocation, event hooks, rate limiting, documentation, and PyPI publishing. After this phase, the package is published and production-ready.

## Prerequisites

- All Phase 2 sub-plans complete

---

## Tasks

### 1. Batch Invocation

**File:** `src/agent_gateway/api/routes/batch.py`

`POST /v1/agents/{agent_id}/batch`:

- Request: `{"items": [{"message": "...", "context": {...}}, ...], "options": {"concurrency": 5, "callback_url": "..."}}`
- Returns 202 with `batch_id`
- Execute items with bounded concurrency (`asyncio.Semaphore`)
- Track per-item results
- `GET /v1/batches/{batch_id}` — status + per-item results
- `POST /v1/batches/{batch_id}/cancel` — cancel remaining items
- Partial success: some items succeed, others fail
- Max batch size: 100 (configurable)
- `callback_url`: fires when entire batch completes
- Per-item notifications follow agent config
- `batch.completed` event when all items done

### 2. Event Hooks (`@gw.on()`)

**File:** `src/agent_gateway/events.py`

```python
class EventEmitter:
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, event: str, handler: Callable) -> None: ...
    async def emit(self, event: str, data: Any) -> None:
        # Run all handlers as background tasks
        # Log failures, never crash
```

Events:
- `execution.started`, `execution.completed`, `execution.failed`, `execution.cancelled`
- `tool.called`, `tool.completed`, `tool.failed`
- `workspace.reloaded`
- `schedule.fired`, `schedule.completed`, `schedule.failed`

Wire into Gateway: `@gw.on("execution.completed")` registers handler.

### 3. Rate Limiting (Optional)

**File:** `src/agent_gateway/api/middleware/rate_limit.py`

- In-memory token bucket (default) or Redis-backed
- Per-key, per-agent limits
- Response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`
- 429 response with standard error envelope
- Configuration in gateway.yaml:
  ```yaml
  rate_limit:
    enabled: false
    requests_per_minute: 60
    backend: memory  # memory | redis
  ```

### 4. `agent-gateway check` Enhancement

Enhance the check command:
- Validate all frontmatter schemas against expected fields
- Check that output_schema is valid JSON Schema
- Validate cron expressions
- Warn on unresolved `${VAR}` in tool configs
- Pretty output with colored checkmarks/crosses

### 5. Mount as Sub-App

Verify and test `app.mount("/agents", gw)`:
- Route prefixing works correctly
- OpenAPI docs merge properly
- Document the pattern in README

### 6. PostgreSQL Support

- Test all persistence operations with asyncpg
- Document connection string format
- Add to CI matrix

### 7. Documentation

- `README.md`: quickstart, core concepts, examples, API reference
- Inline docstrings on all public API methods
- `examples/test-project/` is the living documentation

### 8. PyPI Publishing

- GitHub Actions CI workflow:
  - Matrix: Python 3.11, 3.12, 3.13
  - Steps: lint (ruff), typecheck (mypy), test (pytest with SQLite + PostgreSQL)
  - On tag push: build + publish to PyPI via trusted publishing
- `uv build` produces wheel + sdist
- Verify `pip install agent-gateway` from PyPI works

---

## Tests

- Batch: concurrency limits, partial failure, cancel, callback
- Event hooks: registration, async execution, failure isolation
- Rate limiting: token bucket, 429 response, headers
- Mount as sub-app: routes work with prefix
- PostgreSQL: all persistence tests pass

## Acceptance Criteria

- [ ] Batch invocation with bounded concurrency
- [ ] Event hooks work (`@gw.on()`)
- [ ] Rate limiting (optional)
- [ ] `agent-gateway check` validates comprehensively
- [ ] Mount as sub-app works
- [ ] PostgreSQL tested
- [ ] README complete
- [ ] CI pipeline green
- [ ] Published to PyPI
- [ ] `pip install agent-gateway` works from PyPI
