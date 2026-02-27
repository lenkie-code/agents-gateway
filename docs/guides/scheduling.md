# Scheduling

Agent Gateway can run agents on a schedule using standard cron expressions. Schedules are defined in the agent's `AGENT.md` frontmatter and managed by an embedded [APScheduler](https://apscheduler.readthedocs.io/) instance.

## Defining a Schedule

Add a `schedules` list to the frontmatter of any `AGENT.md`:

```yaml
---
name: report-agent
schedules:
  - name: daily-report
    cron: "0 9 * * 1-5"
    message: "Generate the daily report"
    input: {}
    enabled: true
    timezone: "America/New_York"
---
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique name within this agent |
| `cron` | Yes | Standard 5-field cron expression |
| `message` | Yes | The message sent to the agent when the schedule fires |
| `input` | No | Additional structured input passed alongside the message |
| `enabled` | No | Defaults to `true`. Set to `false` to define but not activate |
| `timezone` | No | IANA timezone name. Defaults to UTC |
| `instructions` | No | Additional instructions injected into the agent's system prompt when this schedule fires. See [Per-Schedule Instructions](#per-schedule-instructions) |

Cron expressions follow the standard 5-field format: `minute hour day-of-month month day-of-week`. For example:

| Expression | Meaning |
|------------|---------|
| `0 9 * * 1-5` | 9:00 AM every weekday |
| `*/15 * * * *` | Every 15 minutes |
| `0 0 1 * *` | Midnight on the first of every month |

### Schedule IDs

Every schedule has a stable ID in the format `{agent_id}:{schedule_name}`. For the example above that would be `report-agent:daily-report`. Use this ID with the management API and CLI.

## Per-Schedule Instructions

The optional `instructions` field lets a single agent behave differently across multiple schedules. When a schedule fires, the value is injected into the agent's system prompt as a dedicated "Schedule Instructions" section — after the agent's base prompt and any user personalization, so it takes precedence for that invocation.

This is useful when:

- One agent produces multiple types of output depending on the day/time (e.g. a social media agent with a "tips" post on Mondays and a "news roundup" on Fridays).
- You want to constrain the agent's response format or focus area for a specific automated run without creating a second agent.

```yaml
---
name: social-media-agent
schedules:
  - name: monday-tips
    cron: "0 9 * * 1"
    message: "Create this week's social media post"
    instructions: "Write a practical tip for Python developers. Use a friendly tone. Keep it under 280 characters."
    timezone: "America/New_York"

  - name: friday-roundup
    cron: "0 9 * * 5"
    message: "Create this week's social media post"
    instructions: "Write a weekly roundup of interesting Python news and releases. Use three bullet points."
    timezone: "America/New_York"
---
```

Instructions are injected only for scheduled firings (including manual triggers via `POST /v1/schedules/{id}/trigger`). They do not affect direct `invoke` or `chat` calls.

!!! note
    Keep instructions concise and focused on the behavioral difference between schedules. For complex agents, think of this field as a "scene-setter" that adjusts tone, format, or focus — not a full replacement for the agent's system prompt. There is no hard character limit enforced by the gateway, but very long instructions will increase token usage for every scheduled run.

!!! note
    Instructions can be edited at runtime from the dashboard schedule edit form without restarting or modifying `AGENT.md`. Runtime edits update APScheduler and the persistence layer but do not write back to `AGENT.md`.

## Gateway Configuration

Enable and tune the scheduler in `gateway.yaml`:

```yaml
scheduler:
  enabled: true
  misfire_grace_seconds: 60
  max_instances: 1
  coalesce: true
```

| Setting | Default | Description |
|---------|---------|-------------|
| `enabled` | `true` | Whether the scheduler runs at all |
| `misfire_grace_seconds` | `60` | How late a job can fire before it is considered missed |
| `max_instances` | `1` | Maximum concurrent instances of the same schedule |
| `coalesce` | `true` | Merge multiple missed firings into one |

## Overlap Prevention

By default `max_instances: 1` prevents a new run from starting while the previous one is still active — the new run is simply skipped. This is the right default for most agents that should not run concurrently.

If a run is still marked active after `2 × misfire_grace_seconds`, the Gateway assumes the previous run was orphaned (e.g. due to a process crash) and force-clears the lock before allowing the next run to proceed.

## Execution Dispatch

When a schedule fires:

- **Queue configured** — the run is enqueued to the queue backend and processed by a worker. This is the recommended path for longer-running agents.
- **No queue** — the run is invoked directly in the scheduler thread. Keep scheduled agents short if you are not using a queue.

## Managing Schedules at Runtime

The Gateway exposes a management API for schedules:

```python
# List all registered schedules and their current state
schedules = await gw.list_schedules()

# Pause a schedule (survives restarts if SQL persistence is configured)
await gw.pause_schedule("report-agent:daily-report")

# Resume a paused schedule
await gw.resume_schedule("report-agent:daily-report")

# Trigger a schedule immediately, outside its normal cadence
await gw.trigger_schedule("report-agent:daily-report")
```

!!! note
    Pause and resume state is only persisted across restarts when a SQL persistence backend is configured. Without persistence, all schedules return to their `AGENT.md` defaults on the next startup.

## CLI

List all registered schedules from the terminal:

```bash
agents-gateway schedules
```

Output shows each schedule's ID, cron expression, timezone, enabled state, and next fire time.

## Multi-Instance Deployment

When running multiple gateway instances behind a load balancer (e.g. with `server.workers > 1` or multiple containers), every instance runs its own embedded scheduler. Without coordination, the same schedule will fire on all instances simultaneously, causing duplicate agent executions.

Enable distributed locking to ensure only one instance fires each scheduled job:

```yaml
scheduler:
  enabled: true
  distributed_lock:
    enabled: true
    backend: auto   # auto | redis | postgres | none
```

### How it works

Before each scheduled job fires, the instance attempts to acquire an exclusive distributed lock for that schedule ID. The instance that wins the lock proceeds with execution; all others skip the firing. The lock expires automatically after `lock_ttl_seconds` (default 300 seconds), so a crashed instance can never hold the lock permanently.

### Backend selection

| Backend | Mechanism | When to use |
|---------|-----------|-------------|
| `auto` | Detects Redis queue → Redis lock; PostgreSQL persistence → PostgreSQL advisory lock | Recommended default |
| `redis` | Redis `SET NX EX` | Explicit Redis lock when queue backend is not Redis |
| `postgres` | `pg_try_advisory_lock` | Explicit PostgreSQL lock without a Redis queue |
| `none` | No-op (same as disabling) | Testing or intentional duplicate-execution tolerance |

With `backend: auto`, the gateway inspects the configured queue and persistence backends at startup:

- Queue backend is Redis → use Redis distributed lock (same connection)
- Persistence backend is PostgreSQL → use PostgreSQL advisory lock
- Neither → fall back to no-op (logs a warning when `enabled: true`)

### Redis backend

```yaml
scheduler:
  distributed_lock:
    enabled: true
    backend: redis
    redis_url: "${REDIS_URL}"   # Defaults to queue.redis_url when omitted
    key_prefix: "ag:sched-lock:"
    lock_ttl_seconds: 300
```

The Redis URL falls back to `queue.redis_url` when not explicitly set, so most Redis-queue deployments need no extra configuration.

### PostgreSQL backend

```yaml
scheduler:
  distributed_lock:
    enabled: true
    backend: postgres
    key_prefix: "ag:sched-lock:"
    lock_ttl_seconds: 300
```

The PostgreSQL backend uses `pg_try_advisory_lock` with a hash of the schedule ID as the lock key. It reuses the existing persistence connection pool — no separate connection string is needed.

### Configuration reference

| Setting | Default | Description |
|---------|---------|-------------|
| `enabled` | `false` | Enable distributed locking. Set to `true` for multi-instance deployments |
| `backend` | `"auto"` | Lock backend: `auto`, `redis`, `postgres`, or `none` |
| `redis_url` | *(from queue)* | Redis connection URL. Defaults to `queue.redis_url` when using the Redis backend |
| `key_prefix` | `"ag:sched-lock:"` | Prefix applied to all lock keys in Redis |
| `lock_ttl_seconds` | `300` | Lock expiry in seconds. Must exceed the maximum expected job duration |

!!! warning
    Set `lock_ttl_seconds` to a value comfortably greater than the longest expected agent execution time. If the lock expires before the job completes, another instance may fire the same schedule.

!!! note
    Distributed locking applies only to **scheduled** job firings. Manual triggers via `POST /v1/schedules/{id}/trigger` always execute regardless of the lock state.

## Admin-Created Schedules

In addition to schedules defined in `AGENT.md` frontmatter, admin users can create and delete **admin schedules** dynamically — without modifying any workspace files or redeploying the gateway.

### How admin schedules differ from workspace schedules

| | Workspace schedule | Admin schedule |
|---|---|---|
| Defined in | `AGENT.md` frontmatter | Dashboard or API at runtime |
| `source` field | `"workspace"` | `"admin"` |
| Survives workspace reload | Yes (re-synced from `AGENT.md`) | Yes (loaded from database) |
| Survives gateway restart | Yes | Yes (re-registered from database on startup) |
| Deletable via API | No | Yes |
| ID format | `{agent_id}:{name}` | `admin:{agent_id}:{name}` |

Workspace schedules are managed exclusively through `AGENT.md`. The API and dashboard will reject attempts to delete them.

### Creating admin schedules via the API

Send a `POST` request to `/v1/schedules`. Requires the `schedules:manage` scope.

```http
POST /v1/schedules
Authorization: Bearer <token>
Content-Type: application/json

{
  "agent_id": "report-agent",
  "name": "weekly-summary",
  "cron_expr": "0 10 * * 1",
  "message": "Generate the weekly executive summary",
  "instructions": "Focus on revenue trends and customer churn. Keep the report under 500 words.",
  "timezone": "Europe/London",
  "enabled": true
}
```

A successful request returns HTTP `201 Created` with the new `schedule_id`.

**Request fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `agent_id` | Yes | ID of the agent to schedule. Must refer to a known agent. |
| `name` | Yes | Unique name within this agent. Alphanumeric, underscores, dots, and hyphens only. |
| `cron_expr` | Yes | Standard 5-field cron expression. |
| `message` | Yes | Message sent to the agent when the schedule fires. |
| `instructions` | No | Per-schedule instructions injected into the system prompt. |
| `input` | No | Additional structured input passed alongside the message. |
| `timezone` | No | IANA timezone name. Defaults to `"UTC"`. |
| `enabled` | No | Whether the schedule is immediately active. Defaults to `true`. |

**Error responses:**

| Status | Condition |
|--------|-----------|
| `400` | Invalid cron expression, unknown `agent_id`, or `name` contains disallowed characters |
| `409` | A non-deleted schedule with the same `agent_id` and `name` already exists |

### Deleting admin schedules via the API

Send a `DELETE` request to `/v1/schedules/{schedule_id}`. Requires the `schedules:manage` scope.

```http
DELETE /v1/schedules/admin:report-agent:weekly-summary
Authorization: Bearer <token>
```

Returns HTTP `200` on success. Returns `400` if the schedule is a workspace schedule (only admin schedules can be deleted this way).

### Creating and deleting admin schedules programmatically

Use the `create_admin_schedule()` and `delete_admin_schedule()` methods on the `Gateway` instance:

```python
# Create an admin schedule
schedule_id = await gw.create_admin_schedule(
    agent_id="report-agent",
    name="weekly-summary",
    cron_expr="0 10 * * 1",
    message="Generate the weekly executive summary",
    instructions="Focus on revenue trends. Keep the report under 500 words.",
    timezone="Europe/London",
)
print(schedule_id)  # "admin:report-agent:weekly-summary"

# Delete it when no longer needed
deleted = await gw.delete_admin_schedule(schedule_id)
```

Both methods return `None` / `False` if the scheduler is not active.

Raises `ScheduleConflictError` if a schedule with the same name already exists for the agent.
Raises `ScheduleValidationError` if the cron expression is invalid or the agent ID is unknown.

### Dashboard

Admin users see a **New Schedule** button on the schedules page at `/dashboard/schedules`. Clicking it opens a form with fields for agent, name, cron expression, message, instructions, timezone, and enabled state.

The schedule list displays a badge for each schedule's origin:

- **Workspace** — defined in `AGENT.md`. Runtime edits are supported; deletion is not.
- **Admin** — created dynamically. A delete button is shown alongside the standard edit controls.

### The `source` field

All schedule list and detail API responses include a `source` field:

```json
{
  "id": "admin:report-agent:weekly-summary",
  "agent_id": "report-agent",
  "name": "weekly-summary",
  "source": "admin",
  "cron_expr": "0 10 * * 1",
  "enabled": true
}
```

Use this field to distinguish admin schedules from workspace schedules in client code.

!!! note
    Admin schedules are loaded from the database on every gateway startup via `_load_admin_schedules`. They are registered with APScheduler alongside workspace schedules and behave identically at runtime — the `source` distinction only affects management operations (creation, deletion, and workspace sync).

!!! warning
    Workspace reloads (triggered by `POST /v1/reload` or the `--reload` flag) only re-sync workspace schedules. Admin schedules in the database are left untouched and remain active after a reload.

## Per-User Schedules

In addition to global schedules defined in `AGENT.md`, users can create personal schedules from the dashboard. These schedules:

- Are scoped to a specific user and stored in the `user_schedules` table
- Can target any agent the user has access to (including configured personal agents)
- Are managed via the dashboard at `/dashboard/my-schedules`
- Support creating, toggling (pause/resume), and deleting schedules
- Use the same cron expression format as global schedules
- Appear on the main schedules page with a "Personal" badge alongside global schedules

Per-user schedules require SQL persistence to be enabled.
