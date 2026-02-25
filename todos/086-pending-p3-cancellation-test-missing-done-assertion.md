---
status: pending
priority: p3
issue_id: "086"
tags: [code-review, quality, tests]
dependencies: []
---

# 086 — `test_asyncio_cancelled_error` does not assert the `done` event status

## Problem Statement

`TestCancellation.test_asyncio_cancelled_error` raises `asyncio.CancelledError` after the
first yielded event, then asserts only that the error propagates via `pytest.raises`.
It does not verify that the generator emits a `done` event with `status == "cancelled"`.

Looking at `streaming.py` lines 434–435:
```python
except asyncio.CancelledError:
    stop_reason = StopReason.CANCELLED
```
The `done` event IS emitted afterward — but only if the generator's `finally`-equivalent
cleanup runs. Because the `CancelledError` is raised from within the consumer (not the
generator body), the generator may be garbage-collected without the `done` event being
consumed.

This is a subtle correctness gap in the test coverage. The test should instead:
1. Cancel a real `asyncio.Task` (not raise manually inside the loop)
2. Verify the generator's finally-path emits `status == "cancelled"`

## Proposed Solutions

### Option A — Cancel the task externally and wait for completion
```python
task = asyncio.create_task(_collect_events(gw, session=session, handle=handle))
await asyncio.sleep(0)  # let it start
task.cancel()
with pytest.raises(asyncio.CancelledError):
    await task
```
- Effort: Small
- Risk: Low — more accurately tests real Task cancellation

### Option B — Mark test as known-limitation, add comment
Document that the test only covers propagation, not cleanup path.
- Effort: Minimal
- Risk: Leaves coverage gap open

## Recommended Action

Option A (or leave as P3 for follow-up).

## Technical Details

- **Affected file:** `tests/test_engine/test_streaming.py`, lines 449–480
- **Related:** `streaming.py` lines 434–435

## Acceptance Criteria

- [ ] Test verifies `done` event with `status == "cancelled"` when a task is externally cancelled

## Work Log

- 2026-02-25: Identified during code review of `feat/streaming-engine-tests`
