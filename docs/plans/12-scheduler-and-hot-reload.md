---
title: "Phase 2.4: Scheduler (Cron) & Hot-Reload"
type: feat
status: pending
date: 2026-02-18
depends_on: [08]
blocks: []
parent: 2026-02-18-feat-agent-gateway-framework-plan.md
---

# Phase 2.4: Scheduler (Cron) & Hot-Reload

## Goal

Cron-based agent invocations and hot-reload of workspace files. After this phase, agents run on schedules and workspace changes are picked up without restart.

## Prerequisites

- Phase 08 (Gateway, execution engine, persistence)

---

## Tasks

### 1. Scheduler Engine

**File:** `src/agent_gateway/scheduler/engine.py`

Integrate APScheduler 4.x (async-native):

- Create `AsyncScheduler` with `SQLAlchemyDataStore` (uses existing DB)
- Register jobs from `WorkspaceState.schedules`
- Each job calls `gw.invoke(agent_id, message, context)` internally
- Context includes `{"source": "scheduled", "schedule_name": "daily-report"}`
- Misfire grace time: configurable (default 60s)
- Max instances per schedule: 1 (prevent overlapping runs)
- Start scheduler in Gateway lifespan (after DB init)
- Stop scheduler in Gateway lifespan shutdown
- Scheduler failure on startup: log warning, continue without schedules

**Job handler:**
```python
async def _run_scheduled_job(
    gateway: Gateway,
    agent_id: str,
    message: str,
    context: dict,
    schedule_name: str,
) -> None:
    try:
        result = await gateway.invoke(agent_id, message, context=context)
        logger.info("Scheduled job '%s' completed: %s", schedule_name, result.stop_reason)
    except Exception:
        logger.exception("Scheduled job '%s' failed", schedule_name)
```

### 2. Schedule Management

- Register/update/remove jobs when workspace reloads
- Diff current schedules vs new schedules:
  - New schedules → add job
  - Modified schedules (cron/message changed) → reschedule job
  - Removed schedules → remove job
  - Disabled schedules → pause job
- Invalid cron expression: warn, skip that schedule

### 3. Schedule API Routes

**File:** `src/agent_gateway/api/routes/schedules.py`

- `GET /v1/schedules` — list all schedules (name, agent, cron, enabled, next run)
- `GET /v1/schedules/{id}` — schedule details + execution history
- `POST /v1/schedules/{id}/run` — manually trigger a scheduled job now
- `POST /v1/schedules/{id}/pause` — pause a schedule
- `POST /v1/schedules/{id}/resume` — resume a paused schedule

### 4. Hot-Reload (File Watcher)

**File:** `src/agent_gateway/workspace/watcher.py`

Async file watcher via `watchfiles`:

- **Filter**: only `.md`, `.yaml`, `.yml`, `.py` files
- **Debounce**: 1600ms (groups rapid changes like git checkout)
- **Watch**: recursive within workspace directory
- **Stop**: via `asyncio.Event`, set in lifespan shutdown

**Reload handler in Gateway:**
```python
async def _on_workspace_change(self, changed_files):
    # 1. Load new workspace (full re-scan)
    # 2. Validate
    # 3. If validation fails: log error, keep old workspace
    # 4. Atomic swap: self._workspace = new_workspace
    # 5. Update tool registry with new file tools
    # 6. Update scheduler with new/changed/removed schedules
    # 7. Log what changed (agents added/removed, etc.)
```

**Robustness:**
- **Reload lock**: `asyncio.Lock()` prevents concurrent reloads
- **Atomic swap**: entire new workspace loaded before swapping
- **Failed reload**: log error, keep old workspace state
- **In-flight executions**: snapshot agent definition at invocation start, not affected by reload
- **Watcher crash recovery**: if watcher task crashes (OS error), restart after 5s delay
- **`POST /v1/reload`**: manual reload endpoint for production

### 5. CLI Commands for Schedules

Update `src/agent_gateway/cli/list_cmd.py`:

- `agent-gateway schedules` — list schedules with next run times
- `agent-gateway schedule-run <name>` — manually trigger

---

## Tests

**Scheduler:**
- Cron expression parsing (valid, invalid)
- Job registration from workspace schedules
- Manual trigger via API
- Pause/resume via API
- Schedule update on reload (add/modify/remove)
- Overlapping run prevention (max_instances=1)
- Failed scheduled execution doesn't crash scheduler
- Schedule introspection API

**Hot-Reload:**
- Add new agent → detected, registered
- Modify AGENT.md → detected, prompt updated
- Delete agent dir → detected, logged as warning
- Add new tool → detected, registered
- Invalid file change → reload fails, old workspace kept
- Concurrent reloads → lock prevents race
- Debounce: rapid changes grouped into single reload
- Manual reload via `POST /v1/reload`

## Acceptance Criteria

- [ ] Schedules parsed from CONFIG.md and registered with APScheduler
- [ ] Scheduled jobs create standard execution records
- [ ] Schedule API endpoints work (list, trigger, pause, resume)
- [ ] Hot-reload detects file changes and updates workspace atomically
- [ ] Failed reload keeps old workspace
- [ ] Schedule changes reflected on hot-reload
- [ ] Watcher crash recovery works
- [ ] `POST /v1/reload` triggers manual reload
- [ ] In-flight executions unaffected by reload
