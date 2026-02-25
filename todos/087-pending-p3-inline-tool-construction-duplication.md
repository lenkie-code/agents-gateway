---
status: pending
priority: p3
issue_id: "087"
tags: [code-review, quality, tests]
dependencies: []
---

# 087 — Inline `CodeTool`/`ResolvedTool` construction duplicated across two test classes

## Problem Statement

`TestToolSchemaValidation.test_invalid_args_rejected` (lines 259–299) and
`TestToolExecutionFailure.test_tool_raises_exception` (lines 302–341) both inline
~25 lines of `CodeTool` + `ResolvedTool` construction. The pattern is identical except
for the tool name, description, `fn`, schema, and `allowed_agents`.

This duplication makes the tests harder to read and will need to be updated in both
places if `CodeTool` or `ResolvedTool` constructors change.

## Proposed Solutions

### Option A — Add helpers to conftest (Recommended)
```python
def make_resolved_tool_strict(
    name: str = "strict_tool",
    fn: ...,
    schema: dict[str, Any] | None = None,
    allowed_agents: list[str] | None = None,
) -> ResolvedTool:
    ...
```
Or more generally, extend `make_resolved_tool` to accept a custom `fn` and `schema`.

### Option B — Leave as-is
Acceptable for test code where explicitness aids debugging.

## Recommended Action

Option A if there are more tests coming that will create custom tools; Option B is fine
if these two are the only cases.

## Technical Details

- **Affected file:** `tests/test_engine/test_streaming.py`

## Acceptance Criteria

- [ ] Inline construction refactored into a shared helper in conftest.py
- [ ] All 28 tests still pass

## Work Log

- 2026-02-25: Identified during code review of `feat/streaming-engine-tests`
