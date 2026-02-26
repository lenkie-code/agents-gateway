---
title: "feat: Super Admin Dashboard Management — Agents, Schedules, Enable/Disable"
type: feat
status: draft
date: 2026-02-26
depends_on: 2026-02-23-feat-superuser-admin-system-plan
---

# feat: Super Admin Dashboard Management

## Overview

Extend the dashboard with admin-only management capabilities: editing agent configuration, enabling/disabling agents at runtime, and managing cron job schedules (update cron expression, message, enable/disable). These features build on the superuser/admin system from the [admin plan](2026-02-23-feat-superuser-admin-system-plan.md) -- all new routes require `is_admin`.

## Problem Statement

Today the dashboard is read-only for agents and nearly read-only for schedules (only toggle exists). Admins cannot:

1. **Edit agents** -- changing an agent's description, model, tags, or instructions requires editing `AGENT.md` on disk and restarting/reloading the gateway.
2. **Enable/disable agents** -- there is no concept of a disabled agent. Removing an agent requires deleting its directory.
3. **Update schedules** -- cron expression, message, and input cannot be changed at runtime. Only the enabled toggle exists.

These limitations force operators to SSH into servers or redeploy to make routine changes.

## Proposed Solution

Add three admin dashboard features behind `require_admin`:

1. **Agent detail/edit page** -- view full agent config and edit mutable fields (description, display_name, tags, model name/temperature, execution_mode). Edits persist to `AGENT.md` frontmatter on disk and trigger a hot-reload.
2. **Agent enable/disable toggle** -- add an `enabled` frontmatter field to `AGENT.md` (defaults to `true`). Toggling writes `enabled: false` to disk and triggers a hot-reload. Disabled agents return 422 from the API and are grayed out in the dashboard.
3. **Schedule edit page** -- edit cron expression, message, timezone, and enabled flag. Changes update both APScheduler and persistence.

**Key design decisions:**

- **Agent edits write to disk.** The workspace is the source of truth. Edits update `AGENT.md` frontmatter and call `gateway.reload()`. This avoids persistence/disk drift.
- **Agent enable/disable writes to disk.** Toggling sets `enabled: false` in `AGENT.md` frontmatter via the same atomic writer utility used for agent edits, then calls `gateway.reload()`. No separate persistence table needed — the workspace is the single source of truth for everything.
- **Schedule edits update both APScheduler and persistence.** The `SchedulerEngine` already has `pause`/`resume`; we add `update_schedule()` for cron/message changes.
- **No AGENT.md body editing from the dashboard.** Editing the full markdown prompt is too risky for a web UI. Only frontmatter fields are editable.

## Scope

### In scope

- Dashboard agent detail page (`GET /dashboard/agents/{agent_id}`) -- admin only
- Dashboard agent edit endpoint (`POST /dashboard/agents/{agent_id}/edit`) -- admin only
- Agent enable/disable toggle (`POST /dashboard/agents/{agent_id}/toggle`) -- admin only
- `enabled` frontmatter field in AGENT.md (defaults to `true` when absent)
- Gateway-level enforcement: disabled agents (`enabled: false`) return 422 from invoke/chat endpoints
- Dashboard schedule detail/edit page (`GET /dashboard/schedules/{schedule_id}/detail`)
- Dashboard schedule update endpoint (`POST /dashboard/schedules/{schedule_id}/edit`) -- admin only
- `SchedulerEngine.update_schedule()` method for cron/message/timezone changes
- All new dashboard routes gated behind `require_admin`
- Example project and documentation updates

### Out of scope

- Creating new agents from the dashboard (requires directory/file creation)
- Deleting agents from the dashboard
- Editing AGENT.md prompt body (only frontmatter metadata)
- Creating new schedules from the dashboard (use `my-schedules` for user schedules)
- Deleting system schedules (they are defined in AGENT.md)
- API-level admin endpoints (future work -- this is dashboard only)

## Prerequisites

1. The superuser/admin system from the [admin plan](2026-02-23-feat-superuser-admin-system-plan.md) must be implemented first (`require_admin` dependency, `admin_emails` config, `is_admin` on sessions).

## Architecture & Design

### Agent Enable/Disable Flow

```
Admin clicks "Disable" on agent card
  -> POST /dashboard/agents/{agent_id}/toggle
  -> Writes `enabled: false` to AGENT.md frontmatter (atomic write)
  -> Calls gateway.reload()
  -> Workspace parser reads `enabled` field (defaults to true when absent)
  -> Invoke/chat routes check agent.enabled -> 422 "Agent is disabled"
  -> Dashboard shows agent as "Disabled" (grayed out card, no Chat button)
```

### Agent Edit Flow

```
Admin opens agent detail page
  -> GET /dashboard/agents/{agent_id}
  -> Renders form with current frontmatter values
Admin submits edit form
  -> POST /dashboard/agents/{agent_id}/edit
  -> Validates input
  -> Updates AGENT.md frontmatter on disk (preserves body)
  -> Calls gateway.reload() to pick up changes
  -> Redirects to agent detail page
```

### Schedule Edit Flow

```
Admin opens schedule detail
  -> GET /dashboard/schedules/{schedule_id}/detail
  -> Renders form with current schedule values
Admin submits edit
  -> POST /dashboard/schedules/{schedule_id}/edit
  -> Validates cron expression
  -> Calls SchedulerEngine.update_schedule()
    -> Removes old APScheduler job
    -> Re-registers with new cron/message
    -> Updates persistence record
  -> Redirects to schedules page
```

## Implementation Steps

### Phase 1: Workspace -- Add `enabled` Field to Agent Model

#### Step 1.1 -- Add `enabled` field to `AgentDefinition`

**File:** `src/agent_gateway/workspace/agent.py`

Add `enabled: bool = True` to the `AgentDefinition` dataclass. This field is read from AGENT.md frontmatter and defaults to `True` when absent (backward compatible).

#### Step 1.2 -- Parse `enabled` from AGENT.md frontmatter

**File:** `src/agent_gateway/workspace/loader.py` (or wherever agent frontmatter is parsed into `AgentDefinition`)

When building `AgentDefinition` from parsed frontmatter, read `enabled` field:

```python
enabled=metadata.get("enabled", True)
```

#### Step 1.3 -- Add `is_agent_enabled()` helper to Gateway

**File:** `src/agent_gateway/gateway.py`

Add a simple public method that checks the agent's `enabled` field from the current workspace snapshot:

```python
def is_agent_enabled(self, agent_id: str) -> bool:
    """Check if an agent is enabled (from AGENT.md frontmatter)."""
    agent = self.agents.get(agent_id)
    if agent is None:
        return False
    return agent.enabled
```

### Phase 2: Agent Disable Enforcement

#### Step 2.1 -- Guard invoke and chat endpoints

**File:** `src/agent_gateway/api/routes/invoke.py`

After agent lookup, before execution, add:

```python
if not agent.enabled:
    return error_response(422, "agent_disabled", f"Agent '{agent_id}' is currently disabled")
```

**File:** `src/agent_gateway/api/routes/chat.py`

Same guard for the chat/stream endpoint.

#### Step 2.2 -- Update introspection to show enabled status

**File:** `src/agent_gateway/api/routes/introspection.py`

Add `"enabled": agent.enabled` to agent info responses in both `list_agents` and `get_agent`.

### Phase 3: Agent Edit -- Disk Write + Reload

#### Step 3.1 -- Add frontmatter write utility

**File:** `/Users/vince/Src/HonesDev/agent-gateway/src/agent_gateway/workspace/writer.py` (new file)

Create a utility to update AGENT.md frontmatter while preserving the markdown body:

```python
import tempfile
from pathlib import Path
from typing import Any

import yaml

from agent_gateway.exceptions import AgentGatewayError
from agent_gateway.workspace.parser import parse_markdown_file


class AgentWriteError(AgentGatewayError):
    """Raised when writing to AGENT.md fails."""


def update_agent_frontmatter(agent_dir: Path, updates: dict[str, Any]) -> None:
    """Update specific frontmatter fields in AGENT.md, preserving body content.

    Only updates fields present in `updates`. Does not remove existing fields.
    Uses atomic write (temp file + rename) to prevent corruption.
    """
    agent_md = agent_dir / "AGENT.md"
    if not agent_md.exists():
        raise AgentWriteError(f"AGENT.md not found in {agent_dir}")

    parsed = parse_markdown_file(agent_md)
    metadata = dict(parsed.metadata)  # copy existing frontmatter

    # Merge updates (shallow for top-level, deep-merge for 'model')
    for key, value in updates.items():
        if key == "model" and isinstance(value, dict) and isinstance(metadata.get("model"), dict):
            metadata["model"] = {**metadata["model"], **value}
        else:
            metadata[key] = value

    # Serialize
    frontmatter = yaml.dump(metadata, default_flow_style=False, sort_keys=False, allow_unicode=True)
    content = f"---\n{frontmatter}---\n\n{parsed.content}"

    # Atomic write
    fd, tmp_path = tempfile.mkstemp(dir=agent_dir, suffix=".md.tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp_path).replace(agent_md)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise
```

**Editable fields whitelist** (enforced at the route handler level, not in the writer):

- `description` (str)
- `display_name` (str or None)
- `tags` (list[str])
- `model.name` (str or None)
- `model.temperature` (float or None)
- `model.max_tokens` (int or None)
- `execution_mode` ("sync" | "async")
- `enabled` (bool, used by the toggle endpoint)

Fields NOT editable from the dashboard (too dangerous or structural):
`skills`, `schedules`, `delegates_to`, `scope`, `input_schema`, `setup_schema`, `notifications`, `context`, `retrievers`, `memory`

### Phase 4: Dashboard Routes -- Agent Management

#### Step 4.1 -- Agent detail page route

**File:** `/Users/vince/Src/HonesDev/agent-gateway/src/agent_gateway/dashboard/router.py`

Add to the `protected` router (after existing agent routes):

```python
@protected.get("/agents/{agent_id}")
async def agent_detail(
    request: Request,
    agent_id: str,
    current_user: DashboardUser = Depends(require_admin),
) -> HTMLResponse:
    """Admin-only agent detail page with edit form."""
    gw = request.app
    agents = gw.agents
    agent = agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    card = AgentCard.from_definition(agent)

    return templates.TemplateResponse(
        "dashboard/agent_detail.html",
        {
            "request": request,
            "agent": agent,
            "card": card,
            "current_user": current_user,
            "dashboard_title": dash_config.title,
            "active_page": "agents",
        },
    )
```

#### Step 4.2 -- Agent edit endpoint

```python
@protected.post("/agents/{agent_id}/edit")
async def agent_edit(
    request: Request,
    agent_id: str,
    current_user: DashboardUser = Depends(require_admin),
    description: str = Form(""),
    display_name: str = Form(""),
    tags: str = Form(""),  # comma-separated
    model_name: str = Form(""),
    model_temperature: str = Form(""),
    model_max_tokens: str = Form(""),
    execution_mode: str = Form("sync"),
) -> RedirectResponse:
    """Update agent frontmatter and reload workspace."""
    gw = request.app
    agent = gw.agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    updates: dict[str, Any] = {}
    updates["description"] = description.strip()
    if display_name.strip():
        updates["display_name"] = display_name.strip()
    if tags.strip():
        updates["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    else:
        updates["tags"] = []

    model_updates: dict[str, Any] = {}
    if model_name.strip():
        model_updates["name"] = model_name.strip()
    if model_temperature.strip():
        try:
            model_updates["temperature"] = float(model_temperature)
        except ValueError:
            pass
    if model_max_tokens.strip():
        try:
            model_updates["max_tokens"] = int(model_max_tokens)
        except ValueError:
            pass
    if model_updates:
        updates["model"] = model_updates

    if execution_mode in ("sync", "async"):
        updates["execution_mode"] = execution_mode

    from agent_gateway.workspace.writer import update_agent_frontmatter
    update_agent_frontmatter(agent.path, updates)
    await gw.reload()

    return RedirectResponse(url=f"/dashboard/agents/{agent_id}", status_code=303)
```

#### Step 4.3 -- Agent toggle (enable/disable) endpoint

```python
@protected.post("/agents/{agent_id}/toggle")
async def toggle_agent(
    request: Request,
    agent_id: str,
    current_user: DashboardUser = Depends(require_admin),
) -> RedirectResponse:
    """Toggle agent enabled/disabled by writing to AGENT.md frontmatter."""
    gw = request.app
    agent = gw.agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_enabled = not agent.enabled
    update_agent_frontmatter(agent.path, {"enabled": new_enabled})
    await gw.reload()

    return RedirectResponse(url="/dashboard/agents", status_code=303)
```

#### Step 4.4 -- Update agent cards template

**File:** `/Users/vince/Src/HonesDev/agent-gateway/src/agent_gateway/dashboard/templates/dashboard/_agent_cards.html`

For admin users, add:
- Agent name becomes a link to `/dashboard/agents/{agent_id}` (the detail page)
- An enable/disable toggle in the card footer (HTMX POST to toggle endpoint)
- Visual indication when disabled: use `card.enabled` to gray out the card and show "Disabled" badge replacing "Online"

#### Step 4.5 -- Create agent detail template

**File:** `/Users/vince/Src/HonesDev/agent-gateway/src/agent_gateway/dashboard/templates/dashboard/agent_detail.html` (new file)

Extends `base.html`. Contains:
- Back link to agents list
- Agent header: avatar/initials, name, description, model, status badge (Online/Disabled)
- Enable/disable toggle button (HTMX POST)
- Edit form section with fields:
  - Description (textarea)
  - Display Name (text input)
  - Tags (text input, comma-separated)
  - Model Name (text input)
  - Model Temperature (number input, step=0.1, min=0, max=2)
  - Model Max Tokens (number input)
  - Execution Mode (select: sync/async)
  - Submit button
- Read-only info section:
  - Skills list
  - Schedules list (linked to schedule detail)
  - Delegates list
  - Scope

Follow the visual style of `agent_setup.html` for form layout and `execution_detail.html` for the detail header pattern.

### Phase 5: Dashboard Routes -- Schedule Management

#### Step 5.1 -- Add `SchedulerEngine.update_schedule()` method

**File:** `/Users/vince/Src/HonesDev/agent-gateway/src/agent_gateway/scheduler/engine.py`

Add method to the `SchedulerEngine` class:

```python
async def update_schedule(
    self,
    schedule_id: str,
    cron_expr: str | None = None,
    message: str | None = None,
    timezone: str | None = None,
    enabled: bool | None = None,
) -> bool:
    """Update a system schedule's configuration at runtime.

    Returns True if the schedule was found and updated.
    """
    if self._scheduler is None:
        return False

    config = self._schedule_configs.get(schedule_id)
    agent_id = self._agent_map.get(schedule_id)
    if config is None or agent_id is None:
        return False

    # Update in-memory ScheduleConfig dataclass
    if cron_expr is not None:
        config.cron = cron_expr
    if message is not None:
        config.message = message
    if timezone is not None:
        config.timezone = timezone
    if enabled is not None:
        config.enabled = enabled

    # Remove and re-register the APScheduler job with new settings
    import contextlib
    with contextlib.suppress(Exception):
        self._scheduler.remove_job(schedule_id)
    await self._register_job(schedule_id, agent_id, config)

    # Update persistence record
    next_run = self._get_next_run_time(schedule_id)
    await self._schedule_repo.update_schedule(
        schedule_id,
        cron_expr=config.cron,
        message=config.message,
        timezone=config.timezone or self._timezone,
        next_run_at=next_run,
    )

    if enabled is not None:
        await self._schedule_repo.update_enabled(schedule_id, enabled)

    return True
```

#### Step 5.2 -- Add `update_schedule` to `ScheduleRepository` protocol

**File:** `/Users/vince/Src/HonesDev/agent-gateway/src/agent_gateway/persistence/protocols.py`

Add to the existing `ScheduleRepository` protocol:

```python
async def update_schedule(
    self,
    schedule_id: str,
    cron_expr: str,
    message: str,
    timezone: str,
    next_run_at: datetime | None = None,
) -> None: ...
```

Implement in both SQL repository and null repository backends.

#### Step 5.3 -- Add `Gateway.update_schedule()` public method

**File:** `/Users/vince/Src/HonesDev/agent-gateway/src/agent_gateway/gateway.py`

```python
async def update_schedule(
    self,
    schedule_id: str,
    cron_expr: str | None = None,
    message: str | None = None,
    timezone: str | None = None,
    enabled: bool | None = None,
) -> bool:
    """Update a schedule's configuration at runtime. Admin operation."""
    if self.scheduler is None:
        return False
    return await self.scheduler.update_schedule(
        schedule_id,
        cron_expr=cron_expr,
        message=message,
        timezone=timezone,
        enabled=enabled,
    )
```

#### Step 5.4 -- Schedule detail/edit page route

**File:** `/Users/vince/Src/HonesDev/agent-gateway/src/agent_gateway/dashboard/router.py`

```python
@protected.get("/schedules/{schedule_id:path}/detail")
async def schedule_detail(
    request: Request,
    schedule_id: str,
    current_user: DashboardUser = Depends(require_admin),
) -> HTMLResponse:
    """Admin-only schedule detail page with edit form."""
    gw = request.app
    schedule = await gw.get_schedule(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    agent_name = schedule["agent_id"]
    agent = gw.agents.get(schedule["agent_id"])
    if agent:
        agent_name = agent.display_name or agent.id

    return templates.TemplateResponse(
        "dashboard/schedule_detail.html",
        {
            "request": request,
            "schedule": schedule,
            "agent_name": agent_name,
            "current_user": current_user,
            "dashboard_title": dash_config.title,
            "active_page": "schedules",
        },
    )


@protected.post("/schedules/{schedule_id:path}/edit")
async def schedule_edit(
    request: Request,
    schedule_id: str,
    current_user: DashboardUser = Depends(require_admin),
    cron_expr: str = Form(...),
    message: str = Form(...),
    timezone: str = Form("UTC"),
    enabled: str = Form("off"),  # checkbox value
) -> RedirectResponse:
    """Update schedule configuration."""
    gw = request.app

    # Validate cron expression
    from apscheduler.triggers.cron import CronTrigger
    try:
        CronTrigger.from_crontab(cron_expr, timezone=timezone)
    except (ValueError, KeyError):
        raise HTTPException(status_code=400, detail="Invalid cron expression")

    # Validate timezone
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, KeyError):
        raise HTTPException(status_code=400, detail="Invalid timezone")

    is_enabled = enabled == "on"

    ok = await gw.update_schedule(
        schedule_id,
        cron_expr=cron_expr,
        message=message,
        timezone=timezone,
        enabled=is_enabled,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return RedirectResponse(url="/dashboard/schedules", status_code=303)
```

#### Step 5.5 -- Create schedule detail template

**File:** `/Users/vince/Src/HonesDev/agent-gateway/src/agent_gateway/dashboard/templates/dashboard/schedule_detail.html` (new file)

Extends `base.html`. Contains:
- Back link to schedules list
- Schedule header: name, agent name, current status (enabled/disabled badge)
- Last run / next run display
- Edit form:
  - Cron Expression (text input with helper text: "5-part cron, e.g. `*/5 * * * *`")
  - Message (textarea)
  - Timezone (text input, default UTC)
  - Enabled (checkbox toggle)
  - Submit button ("Save Changes")

Follow the visual style of `agent_setup.html` for form elements.

#### Step 5.6 -- Update schedules table to add edit links for admins

**File:** `/Users/vince/Src/HonesDev/agent-gateway/src/agent_gateway/dashboard/templates/dashboard/schedules.html`

In the Actions column (line ~111), for admin users, replace the `more_horiz` button with a link to the schedule detail page:

```html
{% if current_user and current_user.is_admin %}
<a href="/dashboard/schedules/{{ s.id }}/detail"
   class="p-1.5 text-slate-500 hover:text-primary transition-colors rounded-lg hover:bg-primary/10"
   title="Edit Schedule">
  <span class="material-symbols-outlined text-base">edit</span>
</a>
{% else %}
<button class="p-1.5 text-slate-500 hover:text-primary transition-colors rounded-lg hover:bg-primary/10">
  <span class="material-symbols-outlined text-base">more_horiz</span>
</button>
{% endif %}
```

### Phase 6: Dashboard Model & Context Updates

#### Step 6.1 -- Update `AgentCard` model

**File:** `src/agent_gateway/dashboard/models.py`

Add `enabled: bool = True` field to the `AgentCard` dataclass. Update `from_definition()` to read it from the `AgentDefinition`:

```python
enabled=agent_def.enabled
```

The template can then use `card.enabled` to show/hide the "Disabled" badge and gray out the card. No need to pass a separate `disabled_agents` set — the `enabled` state lives on the agent definition itself.

### Phase 7: Tests

#### Step 7.1 -- Unit tests for workspace writer

**File:** `/Users/vince/Src/HonesDev/agent-gateway/tests/test_unit/test_workspace_writer.py` (new file)

```python
"""Tests for workspace/writer.py — AGENT.md frontmatter update utility."""

import pytest
from pathlib import Path

from agent_gateway.workspace.writer import update_agent_frontmatter, AgentWriteError


class TestUpdateAgentFrontmatter:
    def test_updates_single_field(self, tmp_path):
        """Updating description preserves other fields and body."""

    def test_preserves_body_content(self, tmp_path):
        """Markdown body after frontmatter is preserved exactly."""

    def test_preserves_unmodified_fields(self, tmp_path):
        """Fields not in updates dict are left unchanged."""

    def test_updates_nested_model_field(self, tmp_path):
        """Updating model.name deep-merges with existing model config."""

    def test_raises_if_agent_md_missing(self, tmp_path):
        """AgentWriteError raised if AGENT.md does not exist."""

    def test_atomic_write_on_error(self, tmp_path):
        """Original file preserved if write fails midway."""
```

#### Step 7.2 -- Integration tests for agent management

**File:** `/Users/vince/Src/HonesDev/agent-gateway/tests/test_integration/test_dashboard_agent_management.py` (new file)

```python
"""Tests for admin agent management features."""

from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

FIXTURE_WORKSPACE = Path(__file__).parent.parent / "fixtures" / "workspace"


class TestAgentDisable:
    async def test_disable_agent_blocks_invoke(self):
        """Disabled agent returns 422 from /v1/agents/{id}/invoke."""

    async def test_disable_agent_blocks_chat(self):
        """Disabled agent returns 422 from /v1/chat."""

    async def test_enable_agent_restores_invoke(self):
        """Re-enabling an agent allows invoke again."""

    async def test_disabled_agent_loaded_from_frontmatter(self):
        """Agent with enabled: false in AGENT.md is disabled after reload."""

    async def test_introspection_shows_enabled_field(self):
        """GET /v1/agents/{id} includes enabled: false."""


class TestAgentEdit:
    async def test_edit_updates_frontmatter_on_disk(self):
        """POST /dashboard/agents/{id}/edit writes to AGENT.md."""

    async def test_edit_triggers_reload(self):
        """Agent definition reflects changes after edit."""

    async def test_edit_requires_admin(self):
        """Non-admin user gets 403."""

    async def test_edit_nonexistent_agent_returns_404(self):
        """Editing unknown agent returns 404."""


class TestAgentToggle:
    async def test_toggle_writes_enabled_false_to_frontmatter(self):
        """Toggle on enabled agent writes enabled: false to AGENT.md."""

    async def test_toggle_writes_enabled_true_to_frontmatter(self):
        """Toggle on disabled agent writes enabled: true to AGENT.md."""

    async def test_toggle_requires_admin(self):
        """Non-admin user gets 403."""


class TestAgentDetailPage:
    async def test_detail_page_renders_for_admin(self):
        """GET /dashboard/agents/{id} returns 200 with agent data."""

    async def test_detail_page_403_for_non_admin(self):
        """Non-admin user gets 403."""
```

#### Step 7.3 -- Integration tests for schedule management

**File:** `/Users/vince/Src/HonesDev/agent-gateway/tests/test_integration/test_dashboard_schedule_management.py` (new file)

```python
"""Tests for admin schedule management features."""

from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

FIXTURE_WORKSPACE = Path(__file__).parent.parent / "fixtures" / "workspace"


class TestScheduleUpdate:
    async def test_update_cron_expression(self):
        """Changing cron updates APScheduler job trigger."""

    async def test_update_message(self):
        """Changing message updates the schedule config."""

    async def test_update_timezone(self):
        """Changing timezone updates the schedule trigger."""

    async def test_update_enabled_flag(self):
        """Toggling enabled pauses/resumes the APScheduler job."""

    async def test_invalid_cron_returns_400(self):
        """Invalid cron expression returns 400."""

    async def test_invalid_timezone_returns_400(self):
        """Invalid timezone returns 400."""

    async def test_edit_requires_admin(self):
        """Non-admin user gets 403."""

    async def test_edit_nonexistent_schedule_returns_404(self):
        """Editing unknown schedule returns 404."""


class TestScheduleDetailPage:
    async def test_detail_page_renders_for_admin(self):
        """GET /dashboard/schedules/{id}/detail returns 200."""

    async def test_detail_page_403_for_non_admin(self):
        """Non-admin user gets 403."""
```

#### Step 7.4 -- Unit tests for `enabled` field parsing

**File:** `/Users/vince/Src/HonesDev/agent-gateway/tests/test_unit/test_agent_enabled_field.py` (new file)

```python
"""Tests for enabled field in AgentDefinition."""

class TestAgentEnabledField:
    def test_defaults_to_true_when_absent(self):
        """Agent without enabled field in frontmatter defaults to enabled=True."""

    def test_reads_enabled_false_from_frontmatter(self):
        """Agent with enabled: false in frontmatter has enabled=False."""

    def test_reads_enabled_true_from_frontmatter(self):
        """Agent with enabled: true in frontmatter has enabled=True."""
```

### Phase 8: Example Project

#### Step 8.1 -- Update example app.py

**File:** `/Users/vince/Src/HonesDev/agent-gateway/examples/test-project/app.py`

Add a comment block documenting admin dashboard testing steps:

```python
# Admin Dashboard Management (requires login as admin):
# 1. Agents page: click agent name -> detail/edit page (admin only)
# 2. Edit description, model, tags -> saves to AGENT.md and reloads
# 3. Disable/enable agent toggle -> disabled agents return 422 on invoke
# 4. Schedules page: click edit icon -> schedule detail/edit page (admin only)
# 5. Edit cron expression, message, timezone -> updates APScheduler live
```

Ensure the example workspace has at least one agent with a schedule so admin features are exercisable.

### Phase 9: Documentation

#### Step 9.1 -- Update dashboard guide

**File:** `/Users/vince/Src/HonesDev/agent-gateway/docs/guides/dashboard.md`

Add an "Admin Management" section after the existing content, covering:
- Agent detail/edit page: which fields are editable and which are not
- Agent enable/disable: how it works (`enabled` frontmatter field, written to AGENT.md, survives restart)
- Schedule editing: how runtime edits relate to AGENT.md definitions
- Note: schedule runtime edits are lost on restart (AGENT.md is the source of truth for schedules)

#### Step 9.2 -- Update configuration reference

**File:** `/Users/vince/Src/HonesDev/agent-gateway/docs/api-reference/configuration.md`

Document the `enabled` frontmatter field for agents.

#### Step 9.3 -- Update gateway API reference

**File:** `/Users/vince/Src/HonesDev/agent-gateway/docs/api-reference/gateway.md`

Add public methods: `is_agent_enabled()`, `update_schedule()`.

#### Step 9.4 -- Update llms.txt

**File:** `/Users/vince/Src/HonesDev/agent-gateway/docs/llms.txt`

Add lines:
- Admin dashboard supports agent editing (frontmatter fields: description, display_name, tags, model, execution_mode)
- Agents can be disabled at runtime via dashboard; disabled agents return 422 from invoke/chat
- Schedules can be edited at runtime (cron, message, timezone, enabled) via admin dashboard

## Alternative Approaches Considered

### 1. Store agent edits in database instead of writing to disk

Pros: no file system access needed, works in containerized environments with read-only filesystems. Cons: drift between disk and runtime, complex merge logic on restart, breaks the "workspace is source of truth" principle. **Rejected** because the workspace-as-source-of-truth pattern is fundamental to the project.

### 2. Agent disable via runtime persistence table (`agent_overrides`)

Store disabled flag in a separate database table; no disk write needed. Pros: fast toggle, no file write. Cons: drift between disk and runtime state, adds a persistence table that must be kept in sync, breaks the "workspace is source of truth" principle. **Rejected** in favor of writing `enabled: false` to AGENT.md frontmatter — consistent with the workspace-as-source-of-truth pattern used for all other agent config.

### 3. Full AGENT.md body editing in the dashboard

Allow editing the markdown prompt text. Pros: complete editing capability. Cons: high risk of accidental prompt corruption, needs a proper code editor component, complex diff/preview UI. **Rejected** for MVP -- only frontmatter metadata is editable.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Writing to AGENT.md from web UI could corrupt the file | Agent fails to load | Atomic write (temp file + rename). Validate YAML frontmatter before write. |
| `gateway.reload()` is not instant -- concurrent requests during reload | Brief inconsistency | Reload uses atomic snapshot swap (already implemented). Requests in-flight use the old snapshot. |
| Schedule cron edits do NOT persist to AGENT.md | Drift between disk and runtime; on restart, AGENT.md values take precedence | Document clearly. Consider adding a "runtime override" indicator in the schedules UI. |
| Agent edit triggers reload, which reverts any runtime schedule edits | Schedule changes lost silently | Document clearly in UI and docs. Future: persist schedule overrides to AGENT.md too. |
| Read-only filesystem (e.g., Docker) prevents agent edits and toggles | Edit/toggle endpoints fail | Return clear error. Document that all admin management features require a writable workspace. |
| Admin edits agent while another admin edits same agent | Last write wins, data loss | Acceptable for MVP. No concurrent edit detection needed at this scale. |

## Verification Checklist

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest -m "not e2e" -x -q
```

- [ ] Agent detail page renders with correct data for admin users
- [ ] Agent detail page returns 403 for non-admin users
- [ ] Agent edit form updates AGENT.md frontmatter on disk
- [ ] Agent edit triggers `gateway.reload()` and changes are reflected
- [ ] Agent toggle writes `enabled: false` to AGENT.md frontmatter and reloads
- [ ] Agents with `enabled: false` return 422 from invoke endpoint
- [ ] Agents with `enabled: false` return 422 from chat endpoint
- [ ] Disabled agents show "Disabled" badge on dashboard agent cards
- [ ] Agent re-enable writes `enabled: true` to AGENT.md and restores operation
- [ ] Agents default to `enabled: true` when field is absent from frontmatter
- [ ] Schedule detail page renders with correct data for admin users
- [ ] Schedule edit updates cron expression in APScheduler
- [ ] Schedule edit updates persistence record (cron, message, timezone)
- [ ] Invalid cron expression returns 400 error
- [ ] Invalid timezone returns 400 error
- [ ] Schedule edit requires admin (403 for non-admin)
- [ ] Agent cards show edit/disable controls only for admin users
- [ ] Schedules table shows edit links only for admin users
- [ ] Introspection endpoint includes `enabled` field in agent info
- [ ] Example project exercises admin features (has agents + schedules)
- [ ] Documentation updated (dashboard guide, config reference, gateway reference, llms.txt)
- [ ] All new files pass mypy strict mode
- [ ] Atomic write prevents AGENT.md corruption on failure

## File Change Summary

| File | Action | Description |
|------|--------|-------------|
| `src/agent_gateway/workspace/agent.py` | Modify | Add `enabled: bool = True` field to `AgentDefinition` |
| `src/agent_gateway/workspace/loader.py` | Modify | Parse `enabled` from AGENT.md frontmatter |
| `src/agent_gateway/workspace/writer.py` | Create | `update_agent_frontmatter()` utility with atomic write |
| `src/agent_gateway/gateway.py` | Modify | Add `is_agent_enabled()`, `update_schedule()` |
| `src/agent_gateway/persistence/protocols.py` | Modify | Add `update_schedule` to `ScheduleRepository` |
| `src/agent_gateway/persistence/null.py` | Modify | Add `update_schedule` to null schedule repo |
| `src/agent_gateway/persistence/backends/sql/repository.py` | Modify | Implement `update_schedule` |
| `src/agent_gateway/api/routes/invoke.py` | Modify | Add disabled agent check (`not agent.enabled`) |
| `src/agent_gateway/api/routes/chat.py` | Modify | Add disabled agent check (`not agent.enabled`) |
| `src/agent_gateway/api/routes/introspection.py` | Modify | Add `enabled` field to agent info |
| `src/agent_gateway/scheduler/engine.py` | Modify | Add `update_schedule()` method |
| `src/agent_gateway/dashboard/router.py` | Modify | Add agent detail, agent edit, agent toggle, schedule detail, schedule edit routes |
| `src/agent_gateway/dashboard/models.py` | Modify | Add `enabled` field to `AgentCard` |
| `src/agent_gateway/dashboard/templates/dashboard/agent_detail.html` | Create | Agent detail/edit page template |
| `src/agent_gateway/dashboard/templates/dashboard/schedule_detail.html` | Create | Schedule detail/edit page template |
| `src/agent_gateway/dashboard/templates/dashboard/_agent_cards.html` | Modify | Add disable toggle and detail link for admins, disabled visual state |
| `src/agent_gateway/dashboard/templates/dashboard/schedules.html` | Modify | Add edit link for admins in actions column |
| `tests/test_unit/test_workspace_writer.py` | Create | Frontmatter writer tests |
| `tests/test_unit/test_agent_enabled_field.py` | Create | Tests for `enabled` field parsing |
| `tests/test_integration/test_dashboard_agent_management.py` | Create | Agent management integration tests |
| `tests/test_integration/test_dashboard_schedule_management.py` | Create | Schedule management integration tests |
| `examples/test-project/app.py` | Modify | Add admin testing instructions comment |
| `docs/guides/dashboard.md` | Modify | Add admin management section |
| `docs/api-reference/configuration.md` | Modify | Document `enabled` frontmatter field |
| `docs/api-reference/gateway.md` | Modify | Document new public methods |
| `docs/llms.txt` | Modify | Add admin management capability lines |
