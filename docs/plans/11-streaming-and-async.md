---
title: "Phase 2.3: Streaming (SSE) & Async Execution"
type: feat
status: pending
date: 2026-02-18
depends_on: [08]
blocks: []
parent: 2026-02-18-feat-agent-gateway-framework-plan.md
---

# Phase 2.3: Streaming (SSE) & Async Execution

## Goal

SSE streaming for real-time token delivery and async execution with polling/callbacks. After this phase, clients can stream agent responses and run long-running agents in the background.

## Prerequisites

- Phase 08 (Gateway, invoke endpoint, execution engine)

---

## Tasks

### 1. SSE Streaming

Modify the invoke endpoint to support streaming:

**Trigger:** `options.stream: true` in request body (canonical) OR `Accept: text/event-stream` header.

**Event types:**
- `event: token` — `data: {"text": "partial "}`
- `event: tool_call` — `data: {"tool": "name", "args": {...}}`
- `event: tool_result` — `data: {"tool": "name", "duration_ms": 340, "success": true}`
- `event: error` — `data: {"message": "error details"}`
- `event: ping` — heartbeat every 15s (prevents proxy timeout)
- `event: done` — `data: {"execution_id": "...", "usage": {...}, "result": {...}}`

**Implementation:**
- Use `StreamingResponse` with `media_type="text/event-stream"`
- Modify executor to yield events via an `asyncio.Queue`
- LLM streaming via `litellm.acompletion(stream=True)`
- Client disconnect: check `await request.is_disconnected()` before each write
- Client disconnect does NOT cancel execution (use explicit cancel)
- Streaming + structured output: stream tokens, validate at end, include in `done` event
- Streaming + approval: emit `event: approval_required` (client must poll separately)

### 2. Async Execution (Memory Backend)

When `options.async: true`:

1. Create execution record (status: `queued`)
2. Start `asyncio.create_task` for the execution
3. Return 202 with `execution_id` and `poll_url`
4. Store `ExecutionHandle` in memory dict (for cancellation)
5. On completion: update execution record, fire notifications, call callback_url

### 3. Cancellation

`POST /v1/executions/{id}/cancel`:
- Look up `ExecutionHandle` in memory
- Set cancel event
- Return 200 with updated status
- Already completed → 409
- Not found (completed and no handle) → check DB, return current status

### 4. Callback URL

When `options.callback_url` is set:
- On execution complete/fail: POST result to callback_url
- Include HMAC signature (same as webhook notifications)
- Retry 3 times with backoff on failure
- Log callback failures

### 5. Memory Backend Limitations

Document clearly:
- In-memory handles lost on server restart
- Async executions lost on restart (no recovery)
- Single-process only
- For production: use Redis backend (Phase 3 / later)

---

## Tests

**Streaming:**
- SSE event sequence: token → tool_call → tool_result → token → done
- Heartbeat ping events
- Client disconnect handling
- Structured output in done event

**Async:**
- Async invocation returns 202
- Poll returns current status
- Poll returns completed result
- Cancel running execution
- Cancel completed execution → 409
- Callback URL called on completion

## Acceptance Criteria

- [ ] SSE streaming delivers tokens in real-time
- [ ] All event types emitted correctly
- [ ] Heartbeat prevents proxy timeout
- [ ] Async execution with polling works
- [ ] Cancellation is cooperative
- [ ] Callback URL called with HMAC signature
- [ ] Memory backend limitations documented
