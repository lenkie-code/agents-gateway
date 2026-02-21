---
title: "feat: Add Server-Rendered Dashboard"
type: feat
status: active
date: 2026-02-21
---

# feat: Add Server-Rendered Dashboard

## Overview

Add a polished, production-grade web dashboard to Agent Gateway served at `/dashboard`. The dashboard is server-rendered with Jinja2 templates, uses HTMX for live partial updates, and Chart.js for analytics visualisations. It has its own separate authentication, is fully customisable (name, logo, theme), and ships bundled inside the Python package.

Design goal: **look better than LangSmith, feel like a premium product.**

---

## Problem Statement / Motivation

Agent Gateway exposes a rich REST API but has no human-friendly interface. Developers debugging executions, product managers checking costs, and ops teams monitoring agent health all need a UI. Today they must either use raw API calls or build their own tooling. A first-class dashboard reduces friction, improves adoption, and makes the project self-contained.

---

## Proposed Solution

A Jinja2 + HTMX dashboard mounted at `/dashboard/*`, entirely outside the `/v1/` auth middleware, with its own lightweight session-based authentication. Five pages cover the full operator workflow:

| Page | Path | Purpose |
|---|---|---|
| Agents | `/dashboard/` | List all agents as beautiful cards |
| Executions | `/dashboard/executions` | Cross-agent execution table with filters |
| Trace | `/dashboard/executions/{id}` | LangSmith-style step-by-step trace |
| Chat | `/dashboard/chat` | Chat with any agent |
| Analytics | `/dashboard/analytics` | Cost, token, and throughput charts |

---

## Design: UI Principles

The dashboard must be **visually excellent**. Key principles:

- **Modern sidebar layout** — fixed left sidebar with icon + label nav, collapsible on mobile
- **Inter font** from Google Fonts (used by Linear, Vercel, Notion)
- **CSS custom properties** for every design token — makes theming trivial
- **Neutral palette with one strong accent colour** — default slate + indigo
- **Cards with subtle shadows and border-radius** — no harsh lines
- **Status badges with semantic colour** — green/yellow/red/blue for completed/queued/failed/running
- **Monospace code blocks** for tool call arguments and LLM outputs — syntax highlighted via Prism.js (CDN)
- **Smooth HTMX transitions** — `htmx-settling` CSS for fade-in on partial swaps
- **Responsive** — works on laptop screens minimum; mobile is secondary

Visual reference: Vercel dashboard (clean), Linear (sidebar), LangSmith (trace view), Posthog (analytics).

---

## Technical Approach

### Package Structure

```
src/agent_gateway/
└── dashboard/
    ├── __init__.py
    ├── router.py           # APIRouter, page handlers, HTMX partials
    ├── auth.py             # DashboardUser, session dependency, login/logout
    ├── models.py           # View models (AgentCard, ExecutionRow, TraceStep, etc.)
    ├── templates/
    │   └── dashboard/
    │       ├── base.html           # Sidebar layout, nav, theme toggle
    │       ├── login.html          # Clean login page
    │       ├── agents.html         # Agents list (full page)
    │       ├── _agent_cards.html   # HTMX partial: agent cards grid
    │       ├── executions.html     # Executions table (full page)
    │       ├── _exec_rows.html     # HTMX partial: table rows
    │       ├── execution_detail.html  # Trace view (full page)
    │       ├── _trace_steps.html   # HTMX partial: step timeline (for polling running)
    │       ├── chat.html           # Chat UI (full page)
    │       ├── _chat_message.html  # HTMX partial: new chat bubble
    │       └── analytics.html      # Analytics (full page)
    └── static/
        └── dashboard/
            ├── tokens.css      # CSS custom property design tokens
            ├── app.css         # Component styles, sidebar, cards, badges
            ├── app.js          # Theme toggle, HTMX config, CSRF, misc
            └── charts.js       # Chart.js init, update helpers
```

Templates and static files are packaged inside the Python distribution (`pyproject.toml` `package-data`). They are loaded via `jinja2.PackageLoader("agent_gateway.dashboard")` so they work correctly from installed wheels.

### Dependencies to Add

```toml
# pyproject.toml [project.dependencies]
"jinja2>=3.1.4",           # template rendering (already in dev deps, make production dep)
"python-multipart>=0.0.9", # Form() support in FastAPI
"itsdangerous>=2.2.0",     # SessionMiddleware cookie signing
```

Optional extra:
```toml
[project.optional-dependencies]
dashboard = ["jinja2>=3.1.4", "python-multipart>=0.0.9", "itsdangerous>=2.2.0"]
```

CDN assets (no bundling required):
- **HTMX 2.x** — `https://unpkg.com/htmx.org@2.0/dist/htmx.min.js`
- **Chart.js 4.x** — `https://cdn.jsdelivr.net/npm/chart.js@4`
- **Inter font** — Google Fonts
- **Prism.js** — syntax highlighting for JSON/tool args

### Routing Architecture

```python
# dashboard/router.py

# Public routes (no auth dependency)
public_router = APIRouter(prefix="/dashboard", include_in_schema=False)
# GET  /dashboard/login
# POST /dashboard/login
# POST /dashboard/logout

# Protected routes (all require session auth)
protected_router = APIRouter(
    prefix="/dashboard",
    include_in_schema=False,
    dependencies=[Depends(get_dashboard_user)],
)
# GET  /dashboard/              → agents page
# GET  /dashboard/agents        → agents page (alias)
# GET  /dashboard/executions    → executions list
# GET  /dashboard/executions/{id} → trace view
# GET  /dashboard/chat          → chat page
# POST /dashboard/chat/send     → HTMX: send message, return chat bubble
# GET  /dashboard/analytics     → analytics page
# GET  /dashboard/partials/*    → all HTMX fragment endpoints
```

Registration in `gateway.py`:
```python
# Called during _register_routes() if dashboard is enabled
from agent_gateway.dashboard.router import register_dashboard
register_dashboard(self)
```

The `/dashboard/static` StaticFiles mount uses `importlib.resources` to resolve the package-internal path.

### HTMX Pattern

Every page endpoint checks for the `HX-Request` header and returns either a full page or the appropriate partial fragment. Full pages use `{% extends "dashboard/base.html" %}`. Partials are standalone fragments without a base.

Key HTMX interactions:
- **Execution list**: polls every 10s for running executions; updates table rows in place
- **Trace view**: polls every 3s while execution status is `running`; stops on completion
- **Chat**: `hx-post` on submit, `hx-target="#messages"`, `hx-swap="beforeend"` to append new bubbles; submit button disabled while request is in-flight
- **Analytics date range**: `hx-get` on select change, replaces chart data

CSRF: All HTMX mutating requests include `X-CSRF-Token` header (injected via `htmx:configRequest` event hook). Token generated per-session, stored in `request.session`.

---

## Configuration

### DashboardConfig Model

```python
# config.py — added to GatewayConfig

class DashboardAuthConfig(BaseModel):
    enabled: bool = True
    username: str = "admin"
    password: str = ""          # empty = no password (insecure default, warned at startup)
    session_secret: str = ""    # auto-generated if empty

class DashboardThemeConfig(BaseModel):
    mode: Literal["light", "dark", "auto"] = "auto"
    accent_color: str = "#6366f1"       # indigo default
    accent_color_dark: str = "#818cf8"  # indigo-400 for dark mode

class DashboardConfig(BaseModel):
    enabled: bool = False          # opt-in
    title: str = "Agent Gateway"
    logo_url: str | None = None
    favicon_url: str | None = None
    auth: DashboardAuthConfig = DashboardAuthConfig()
    theme: DashboardThemeConfig = DashboardThemeConfig()

class GatewayConfig(BaseSettings):
    # ... existing fields ...
    dashboard: DashboardConfig = DashboardConfig()
```

`gateway.yaml` example:
```yaml
dashboard:
  enabled: true
  title: "My AI Platform"
  logo_url: "https://example.com/logo.svg"
  auth:
    username: admin
    password: "s3cr3t"
  theme:
    mode: dark
    accent_color: "#f59e0b"
```

### Fluent API

```python
# gateway.py
def use_dashboard(
    self,
    *,
    title: str | None = None,
    logo_url: str | None = None,
    auth_username: str | None = None,
    auth_password: str | None = None,
    theme: Literal["light", "dark", "auto"] | None = None,
    accent_color: str | None = None,
) -> "Gateway":
    """Enable and configure the dashboard."""
    ...
    return self
```

Usage:
```python
gw = Gateway()
gw.use_dashboard(
    title="Acme AI Hub",
    logo_url="https://acme.com/logo.svg",
    auth_username="admin",
    auth_password="hunter2",
    theme="dark",
    accent_color="#f59e0b",
)
```

---

## Data Layer Changes Required

Several gaps in the current data layer must be resolved before the dashboard can be built.

### 1. Add `ExecutionRepository.list_all()`

The current `list_executions` API route returns `[]` when no `agent_id` is provided (existing `TODO`). A new method is needed:

```python
# persistence/backends/sql/repository.py
async def list_all(
    self,
    limit: int = 50,
    offset: int = 0,
    agent_id: str | None = None,
    status: str | None = None,
    since: datetime | None = None,
) -> list[ExecutionRecord]:
    ...
```

File: `src/agent_gateway/persistence/backends/sql/repository.py`

### 2. Add Analytics Aggregation Methods

```python
# persistence/backends/sql/repository.py
async def cost_by_day(self, days: int = 30) -> list[dict]:
    """Returns [{date, total_cost_usd, total_input_tokens, total_output_tokens}]"""

async def cost_by_agent(self, days: int = 30) -> list[dict]:
    """Returns [{agent_id, total_cost_usd, execution_count}]"""

async def executions_by_day(self, days: int = 30) -> list[dict]:
    """Returns [{date, count, success_count, failed_count}]"""
```

These use JSON extraction on the `usage` column (`JSON_EXTRACT` for SQLite, `->>'field'` for Postgres).

### 3. Verify / Add Step Recording in Executor

**Critical:** Review `engine/executor.py` to confirm `add_step()` is called after each LLM call and tool call/result. Based on code analysis, this may not be implemented yet. If missing, add step recording:

```python
# engine/executor.py — inside _execute_loop()

# After each LLM call:
await self._execution_repo.add_step(ExecutionStep(
    execution_id=execution_id,
    step_type="llm_call",
    sequence=step_seq,
    data={
        "model": llm_response.model,
        "input_tokens": llm_response.input_tokens,
        "output_tokens": llm_response.output_tokens,
        "cost_usd": llm_response.cost,
        "stop_reason": llm_response.stop_reason,
        "content": llm_response.content[:4096],  # truncate for storage
    },
    duration_ms=elapsed_ms,
))

# After each tool call result:
await self._execution_repo.add_step(ExecutionStep(
    execution_id=execution_id,
    step_type="tool_call",
    sequence=step_seq,
    data={
        "tool_name": tool_name,
        "arguments": tool_args,
    },
    duration_ms=0,
))

await self._execution_repo.add_step(ExecutionStep(
    execution_id=execution_id,
    step_type="tool_result",
    sequence=step_seq,
    data={
        "tool_name": tool_name,
        "result": result_str[:4096],
        "truncated": len(result_str) > 4096,
    },
    duration_ms=tool_elapsed_ms,
))
```

### 4. ExecutionStep Data Schema (Document)

| `step_type` | `data` fields |
|---|---|
| `llm_call` | `model`, `input_tokens`, `output_tokens`, `cost_usd`, `stop_reason`, `content` (str, truncated) |
| `tool_call` | `tool_name`, `arguments` (dict) |
| `tool_result` | `tool_name`, `result` (str, truncated), `truncated` (bool) |

---

## Implementation Phases

### Phase 1: Foundation (Config + Package Structure)

1. Add `DashboardConfig` to `config.py` and `GatewayConfig`
2. Create `src/agent_gateway/dashboard/` package with `__init__.py`, `router.py`, `auth.py`, `models.py`
3. Add `dashboard/templates/` and `dashboard/static/` directories; declare in `pyproject.toml` package-data
4. Wire `Jinja2Templates` with `PackageLoader("agent_gateway.dashboard")`
5. Mount `StaticFiles` using `importlib.resources` for package-relative path
6. Implement `use_dashboard()` fluent method on `Gateway`
7. Register `SessionMiddleware` (Starlette) only when dashboard is enabled
8. Implement `get_dashboard_user` session dependency, login/logout endpoints
9. Write login page template (`login.html`) — clean, centered card, error flash

**Acceptance:**
- `gw.use_dashboard(...)` mounts `/dashboard/login` with a styled login page
- Valid credentials set a session cookie and redirect to `/dashboard/`
- Invalid credentials re-render the form with an error message
- All routes except login/logout redirect to `/dashboard/login` without a valid session

### Phase 2: CSS Design System + Base Layout

1. Author `tokens.css` — full set of CSS custom properties (colors, spacing, font, radius, shadow)
2. Author `app.css` — sidebar layout, nav items, card component, badge component, table styles, button styles, empty state component
3. Author `base.html` — sidebar with nav icons + labels, top bar with title/logo, theme toggle button, HTMX + Chart.js + Prism.js CDN includes, CSRF meta tag
4. Inject `DashboardConfig` context (title, logo, accent color) into every template via a Jinja2 global or middleware
5. Implement theme toggle (CSS class `dark` on `<html>`, persisted to `localStorage`)
6. Author `app.js` — theme toggle logic, HTMX CSRF injection, HTMX `htmx:configRequest` hook

**Acceptance:**
- Base layout renders with sidebar, nav, content area
- Light/dark mode toggle works; preference persists on refresh
- Custom `accent_color` from config is injected as `--color-accent` CSS variable inline in `<head>`
- Custom `logo_url` renders in the sidebar header; falls back to text-based wordmark

### Phase 3: Agents Page

1. Implement `GET /dashboard/` and `GET /dashboard/agents` (full page + HTMX partial)
2. Build `AgentCard` view model from `AgentDefinition`:
   - Name, description, tags (pill badges), model name, execution mode, skills count
   - "Last execution" status badge (requires a `get_last_execution_for_agent()` query, or omit if too costly)
   - Link to chat with this agent, link to executions filtered by agent
3. Design agent card: avatar/icon (derived from agent name initials or emoji), gradient header accent, hover lift effect
4. Empty state when no agents in workspace
5. "Workspace degraded" banner when `workspace.errors` is non-empty

**Acceptance:**
- All agents in the workspace render as cards in a responsive grid
- Clicking "Chat" navigates to `/dashboard/chat?agent_id={id}`
- Clicking "Executions" navigates to `/dashboard/executions?agent_id={id}`

### Phase 4: Executions List + Repository Changes

1. Implement `ExecutionRepository.list_all()` with filtering and pagination
2. Implement `GET /dashboard/executions` (full page + HTMX partial for rows)
3. Build `ExecutionRow` view model: id (truncated), agent name, status badge, started_at, duration, cost, message preview
4. Design table: sortable headers (client-side for now), status colour badges, alternating row hover
5. Status filter tabs: All / Running / Completed / Failed (HTMX partial swap)
6. Agent filter dropdown (from workspace agent list)
7. Pagination: simple prev/next with current page indicator
8. Running executions show a pulsing badge; page auto-polls every 10s while any `running` rows exist (HTMX `hx-trigger="every 10s [document.querySelector('.status-running')]"`)
9. Empty state with contextual message (no executions yet / no persistence configured)

**Acceptance:**
- Cross-agent execution list renders with status, duration, cost columns
- Running executions update in place without full page reload
- Filter by agent and status works

### Phase 5: Execution Trace (Detail View)

1. Confirm or implement step recording in `engine/executor.py` (see Data Layer section)
2. Implement `GET /dashboard/executions/{id}` (full page + polling partial)
3. Build `TraceStep` view model: step type, sequence, duration badge, expandable data
4. Design trace timeline — vertical timeline with connector lines (like LangSmith):
   - **LLM call node**: model chip, input/output token counts, cost, stop reason, expandable content preview
   - **Tool call node**: tool name badge, collapsible JSON arguments (Prism.js highlighted)
   - **Tool result node**: collapsible result (truncated at 500 chars with "show more"), truncation warning if flagged
   - Parallel tool calls grouped visually under the parent LLM call
5. Header summary: agent name, status badge, total duration, total cost, model(s) used
6. If execution is `running`: poll every 3s for new steps; stop polling on completion
7. Error state: show error message prominently if status is `failed`
8. Empty steps state: notice that "step recording may not be enabled"

**Acceptance:**
- Execution with steps renders a clear timeline with expandable tool call details
- JSON in tool call arguments is syntax-highlighted
- Parallel tool calls are visually distinct from sequential ones
- Running executions show live updates via HTMX polling

### Phase 6: Chat Page

1. Implement `GET /dashboard/chat` (full page)
2. Agent selector: dropdown populated from workspace agents, defaults to `?agent_id=` query param
3. Session management: store `session_id` in Jinja2 template hidden field; created server-side on first message
4. Message input: text area with `Shift+Enter` for newline, `Enter` to send
5. `POST /dashboard/chat/send`: HTMX endpoint — creates session if needed, calls agent, returns `_chat_message.html` fragment
6. Design chat UI:
   - User messages: right-aligned, accent colour bubble
   - Agent messages: left-aligned, surface colour bubble, agent avatar initials
   - Loading indicator (animated dots) while HTMX request is in-flight
   - Message timestamps (relative: "just now", "2m ago")
   - Markdown rendering in agent responses — use `marked.js` (CDN) to render markdown client-side after HTMX swap via `htmx:afterSwap` hook
7. Submit button disabled while request in-flight (HTMX `hx-disabled-elt="find button"`)
8. Switching agents shows a "Started new conversation with {agent}" system message
9. Session expiry (30 min): graceful "session expired, starting fresh" notice

**Acceptance:**
- User can select an agent, send a message, and see a formatted response
- Switching agents starts a new visual conversation thread
- Markdown in agent responses (bold, code, lists) renders correctly
- Submit is disabled during the request to prevent double-send

### Phase 7: Analytics Page

1. Implement analytics repository methods (`cost_by_day`, `cost_by_agent`, `executions_by_day`)
2. Implement `GET /dashboard/analytics` (full page with initial Chart.js data)
3. Date range selector: Last 7 days / 30 days / 90 days (HTMX updates chart data via `data-` attributes)
4. Charts (Chart.js, line/bar/doughnut):
   - **Cost over time** — line chart, daily total cost USD (line + area fill)
   - **Executions over time** — stacked bar chart (completed / failed per day)
   - **Cost by agent** — horizontal bar chart (top N agents)
   - **Token usage** — dual-axis line chart (input vs output tokens)
5. Summary stats strip: total cost (period), total executions, avg duration, success rate
6. Chart colours use CSS variables via `getComputedStyle` so they respond to theme changes
7. Empty state per chart when no data in period
8. "No persistence backend" notice when persistence is disabled

**Acceptance:**
- All four charts render with real data from the database
- Date range change refreshes charts via HTMX without full page reload
- Charts update colours correctly when switching between light/dark mode

---

## Acceptance Criteria

### Functional

- [ ] Dashboard is disabled by default; enabled via `gateway.yaml` or `use_dashboard()`
- [ ] Login page with username/password; session cookie issued on success
- [ ] All protected pages redirect to login without a valid session
- [ ] Agents page: lists all workspace agents as styled cards
- [ ] Executions page: cross-agent list with status filter, agent filter, pagination
- [ ] Execution detail: step-by-step trace with LLM calls, tool calls, tool results
- [ ] Chat page: agent selector, message input, streamed response display
- [ ] Analytics page: 4 charts with date range selector
- [ ] Dashboard customisation: title, logo, theme mode, accent colour all work
- [ ] HTMX partial updates work on executions list and trace view without full reload
- [ ] No JS framework required beyond HTMX + Chart.js (both CDN)

### Non-Functional

- [ ] Dashboard bypasses `/v1/` auth middleware (session auth is independent)
- [ ] Templates and static files are packaged inside the Python wheel
- [ ] CSS custom properties enable theming; accent colour is injected from config
- [ ] Light/dark mode works; preference persists in `localStorage`
- [ ] Works with both SQLite and Postgres backends
- [ ] No dashboard routes appear in the OpenAPI schema
- [ ] CSRF protection on all mutating HTMX requests
- [ ] Passwords stored hashed (use `hashlib.sha256` or `secrets.compare_digest`)

### Quality

- [ ] Unit tests for `DashboardConfig` defaults and validation
- [ ] Unit tests for `ExecutionRepository.list_all()` and analytics queries
- [ ] Unit tests for `get_dashboard_user` dependency (valid/invalid/expired session)
- [ ] Integration test: `GET /dashboard/login` returns 200 with correct HTML
- [ ] Integration test: unauthenticated `GET /dashboard/` redirects to login
- [ ] Example project (`examples/test-project/`) updated with dashboard enabled

---

## Dependencies & Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Execution steps not recorded in executor | High | Audit `executor.py` first; add step recording as Phase 0 if missing |
| SQLite JSON aggregation queries are slow on large datasets | Medium | Add index on `executions.created_at`; warn in docs for large deployments |
| Chart.js CDN unavailable in air-gapped environments | Low | Document; add `dashboard.chart_js_url` config override in future |
| Session middleware conflicts with existing middleware stack | Low | `SessionMiddleware` is stateless; use unique cookie name `agw_dashboard_session` |
| `itsdangerous` not in production deps | Certain | Add to `[project.dependencies]`; already in dev env |

---

## Future Considerations

- **Pagination via cursor** instead of offset (better for large execution tables)
- **Real-time execution feed** via SSE (Server-Sent Events) — HTMX supports `hx-ext="sse"`
- **Role-based access** — viewer vs admin (admin can trigger agent invocations from dashboard)
- **Execution search** — full-text search on message/result content
- **Chat history persistence** — save chat sessions to the persistence backend
- **Dashboard API token auth** — alternative to username/password for headless access
- **Multi-tenant dashboard** — scoped views per API key / team

---

## References & Research

### Internal

- `src/agent_gateway/gateway.py:82` — `Gateway` class; route registration in `_register_routes()`
- `src/agent_gateway/config.py` — `GatewayConfig`, `AuthConfig` patterns to follow for `DashboardConfig`
- `src/agent_gateway/persistence/domain.py` — `ExecutionRecord`, `ExecutionStep` data classes
- `src/agent_gateway/persistence/backends/sql/repository.py` — `ExecutionRepository` methods
- `src/agent_gateway/engine/executor.py` — execution loop; where to add step recording
- `src/agent_gateway/engine/models.py:57` — `UsageAccumulator` (cost tracking)
- `src/agent_gateway/workspace/agent.py:49` — `AgentDefinition` fields
- `src/agent_gateway/notifications/template.py` — existing Jinja2 sandbox usage
- `src/agent_gateway/api/routes/executions.py:83` — existing `list_executions` TODO

### External

- [FastAPI Templates docs](https://fastapi.tiangolo.com/advanced/templates/)
- [Jinja2 `PackageLoader` API](https://jinja.palletsprojects.com/en/stable/api/)
- [HTMX + FastAPI patterns](https://testdriven.io/blog/fastapi-htmx/)
- [fasthx — HTMX decorators for FastAPI](https://github.com/volfpeter/fasthx)
- [Chart.js 4 docs](https://www.chartjs.org/docs/latest/)
- [Starlette `SessionMiddleware`](https://www.starlette.io/middleware/#sessionmiddleware)
