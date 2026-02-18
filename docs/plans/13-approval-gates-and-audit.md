---
title: "Phase 2.5: Approval Gates & Audit Log"
type: feat
status: pending
date: 2026-02-18
depends_on: [08, 10]
blocks: []
parent: 2026-02-18-feat-agent-gateway-framework-plan.md
---

# Phase 2.5: Approval Gates & Audit Log

## Goal

Human-in-the-loop approval for sensitive tool executions and comprehensive audit logging. After this phase, tools marked `require_approval: true` pause execution and wait for human approval.

## Prerequisites

- Phase 08 (execution engine)
- Phase 10 (notifications — for sending approval requests)

---

## Tasks

### 1. Approval Gate Logic

**File:** `src/agent_gateway/engine/approval.py`

When the executor encounters a tool with `require_approval: true`:

1. Set execution status to `approval_pending`
2. Save pending tool call details to DB
3. Fire `approval.required` notification (Slack button, webhook)
4. **Pause the execution timeout clock**
5. Wait on an `asyncio.Event` for approval/denial
6. On approve: resume execution, execute the tool, continue loop
7. On deny: terminate execution with `denied` status

**Approval state stored in DB:**
```python
# Add to execution record or separate table
approval_tool_name: str
approval_tool_args: dict
approval_requested_at: datetime
approval_resolved_at: datetime | None
approval_decision: str | None  # "approved" | "denied"
approval_actor: str | None     # Who approved
```

### 2. Approval API Endpoints

- `POST /v1/executions/{id}/approve` — resume execution
  - Body: `{"approved_by": "user@example.com"}` (optional)
  - Requires `executions:approve` scope
  - Returns 200 with updated execution status
  - Returns 409 if not in `approval_pending` state
  - Race condition: first call wins, subsequent → 409

- `POST /v1/executions/{id}/deny` — terminate execution
  - Body: `{"denied_by": "user@example.com", "reason": "..."}`
  - Returns 200 with denied status
  - Returns 409 if not in `approval_pending` state

### 3. Timeout Clock Pause

Modify executor to track elapsed time separately from wall time:
- When entering `approval_pending`, record time spent so far
- When resuming after approval, subtract already-spent time from remaining timeout
- If no timeout configured, no special handling needed

### 4. Audit Log

**File:** `src/agent_gateway/persistence/audit.py`

Events to log:
- `execution.started` — agent_id, execution_id, message (truncated), caller identity
- `execution.completed` — execution_id, status, duration_ms
- `execution.failed` — execution_id, error
- `tool.called` — execution_id, tool_name, agent_id
- `auth.success` — identity, IP, scopes
- `auth.failure` — IP, reason
- `approval.requested` — execution_id, tool_name
- `approval.granted` — execution_id, actor
- `approval.denied` — execution_id, actor, reason
- `workspace.reloaded` — changed files count
- `schedule.fired` — schedule_name, agent_id

Non-blocking: use `asyncio.create_task` for writes.

---

## Tests

**Approval:**
- Tool with require_approval pauses execution
- Approve → execution resumes and completes
- Deny → execution terminates with denied status
- Double approve → 409
- Approve non-pending execution → 409
- Timeout clock paused during approval
- Approval persisted in DB (survives Gateway reference, queryable)

**Audit:**
- Events logged for all specified event types
- Non-blocking (doesn't slow execution)
- Queryable via DB

## Acceptance Criteria

- [ ] Approval gates pause execution and wait for human input
- [ ] Approve/deny API endpoints work with race condition handling
- [ ] Timeout clock pauses during approval
- [ ] Approval state persisted in DB
- [ ] Notification sent on approval request
- [ ] Audit log captures all specified events
- [ ] Audit writes are non-blocking
