---
status: pending
priority: p2
issue_id: "085"
tags: [code-review, quality, tests]
dependencies: []
---

# 085 — `test_semaphore_limits_concurrency` assertion does not prove mutual exclusion

## Problem Statement

`TestConcurrencySemaphore.test_semaphore_limits_concurrency` only asserts that both
tasks complete (`len(order) == 2`). It does NOT verify that the semaphore actually
serialised the two concurrent streams. If the semaphore were removed from
`stream_chat_execution`, this test would still pass.

## Findings

- **File:** `tests/test_engine/test_streaming.py`, lines 483–516

```python
await asyncio.gather(t1, t2)
# Both should complete (order may vary, but both finish)
assert len(order) == 2
```

The comment "order may vary" signals the author knows ordering is non-deterministic, but
mutual exclusion (only one stream inside the semaphore at a time) is testable via a
shared counter.

## Proposed Solutions

### Option A — Track concurrent-in-flight count (Recommended)
```python
in_flight = 0
max_in_flight = 0

async def _run(label: str) -> None:
    nonlocal in_flight, max_in_flight
    session = ChatSession(session_id=f"sess_{label}", agent_id=agent.id)
    handle = ExecutionHandle(execution_id=f"exec_{label}")
    async for _ in stream_chat_execution(...):
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
    in_flight -= 1
    order.append(label)

await asyncio.gather(t1, t2)
assert len(order) == 2
assert max_in_flight == 1  # semaphore(1) means at most 1 concurrent stream
```
- Effort: Small
- Risk: None — adds a meaningful assertion

### Option B — Leave as a smoke test, add a comment
Add a comment explaining the test is a liveness check only, not a mutual-exclusion check.
Not ideal but acceptable if the team prefers not to add complexity.

## Recommended Action

Option A.

## Technical Details

- **Affected file:** `tests/test_engine/test_streaming.py`

## Acceptance Criteria

- [ ] Test asserts `max_in_flight == 1` (or equivalent proof of serial execution)
- [ ] All 28 tests still pass

## Work Log

- 2026-02-25: Identified during code review of `feat/streaming-engine-tests`
