---
title: "Role-Based Dashboard Page Access Restrictions"
type: feat
status: completed
date: 2026-02-27
---

# Role-Based Dashboard Page Access Restrictions

## Overview

Restrict dashboard pages by user role: Analytics and Executions pages are admin-only, Conversations page shows only the logged-in user's data. Non-admin users see a reduced sidebar with only the pages they can access.

## Out of Scope

- The `delegate_to` built-in tool (inter-agent delegation) creates child executions internally. Propagating `user_id` through delegation chains will be planned separately.

## Problem Statement

Currently all authenticated dashboard users can see all pages and all data. There is no distinction between admin and regular users in terms of page visibility or data scoping. The `require_admin` dependency exists and is used on some routes (agent management, schedule management), but Analytics, Executions, and Conversations pages are open to all authenticated users.

## Proposed Solution

1. **Analytics & Executions**: Change dependency from `get_dashboard_user` to `require_admin`
2. **Conversations**: Filter by current user's username (using `session_id` ownership or adding a `user_id` filter parameter)
3. **Sidebar**: Pass `current_user` to `base.html` and conditionally render nav links
4. **Non-admin access to restricted pages**: The existing `AdminRequiredError` handler redirects to `/dashboard/agents` (303)

## Technical Approach

### Key Discovery: No `user_id` on `executions` Table

The `executions` table has no `user_id` column. The `conversations` table (used for chat rehydration) does have `user_id`, but the dashboard Conversations page queries from `executions` grouped by `session_id`. There are two options for scoping conversations:

- **Option A (recommended)**: Add a `user_id` column to `executions` and a migration. This is the correct long-term solution.
- **Option B**: Filter conversations by matching the `session_id` pattern or `options` JSON field. Fragile and not recommended.

**Recommendation**: Option A. Add `user_id` to `ExecutionRecord` and `executions` table, with a new migration. The conversations query can then filter by `user_id`. The API invoke path already has access to user identity via `AuthResult`.

### Implementation Phases

#### Phase 0: Startup Enforcement — Admin Credentials Required

**File: `src/agent_gateway/gateway.py`** — In `_do_startup()`, after dashboard config is merged (where pending dashboard config is applied):

- After the dashboard config is resolved but before the dashboard router is mounted, add a check: if the dashboard is enabled and auth is enabled **and OAuth2 is NOT configured** (`not dash_config.auth.oauth2`), verify that `admin_username` and `admin_password` are both non-None and non-empty strings. If either is missing, raise `ConfigError` with a clear message, e.g.: `"Dashboard requires admin_username and admin_password when password auth is enabled. Set both to define the super-admin account."`
- **Important**: This check must NOT apply to OAuth2 dashboards — in OAuth2 mode, admin status is derived from JWT claims and there is no `admin_username`/`admin_password` concept. The condition is: `if dash_config.auth.enabled and not dash_config.auth.oauth2 and (not admin_username or not admin_password): raise ConfigError(...)`
- Import `ConfigError` from `agent_gateway.exceptions`.
- This prevents the gateway from starting without admin credentials, which would leave all users as non-admin with no way to access admin pages.

**File: `src/agent_gateway/dashboard/auth.py`** — Fix `AdminRequiredError`:

- Change `class AdminRequiredError(Exception)` to `class AdminRequiredError(AgentGatewayError)`.
- Add import: `from agent_gateway.exceptions import AgentGatewayError`.

#### Phase 1: Schema Change — Add `user_id` to Executions

**File: `src/agent_gateway/persistence/domain.py`**
- Add `user_id: str | None = None` field to `ExecutionRecord` (after `session_id`)

**File: `src/agent_gateway/persistence/backends/sql/base.py`**
- Add `Column("user_id", String, nullable=True)` to `executions` table
- Add index `ix_{prefix}executions_user_id` on `user_id`

**File: `src/agent_gateway/persistence/migrations/versions/011_add_user_id_to_executions.py`** — New migration with `revision = "011"` and `down_revision = "010"`:
- `ALTER TABLE executions ADD COLUMN user_id VARCHAR`
- `CREATE INDEX ix_executions_user_id ON executions(user_id)`

**File: `src/agent_gateway/api/routes/invoke.py`** — The primary `ExecutionRecord` creation site (lines 167-177):
- The `auth`/`user_id` derivation currently happens at lines 220-221 (after the record is already created and persisted). Move the derivation **above** the `ExecutionRecord` construction:
  ```python
  # Derive user_id from auth context (before creating execution record)
  auth = request.scope.get("auth")
  user_id = gw._derive_user_id(auth) if auth else None
  ```
- Pass `user_id=user_id` to the `ExecutionRecord(...)` constructor at line 169.
- Remove the duplicate `auth`/`user_id` derivation at lines 220-221 (it is now done earlier and the variable is already in scope).

**File: `src/agent_gateway/scheduler/engine.py`** — Two `ExecutionRecord` creation sites (lines 320 and 422):
- Scheduler-fired executions have no authenticated user. These already create `ExecutionRecord` without `user_id`, which will default to `None`. No change needed — just confirm that the new `user_id` field defaults to `None` in the dataclass, so these callsites continue to work without modification. Add a code comment: `# user_id=None for scheduler-initiated executions`.

#### Phase 2: Repository Changes — User-Scoped Queries

**File: `src/agent_gateway/persistence/protocols.py`**
- Add `user_id: str | None = None` parameter to `list_conversations_summary()`
- Add `user_id: str | None = None` parameter to `count_conversations()`

**File: `src/agent_gateway/persistence/backends/sql/repository.py`**
- Update `list_conversations_summary()` (line 301): add `user_id: str | None = None` parameter. When `user_id` is not None, append `AND user_id = :user_id` to the WHERE clause and add `"user_id": user_id` to the bound parameters dict. **Use bound parameters (`:user_id`) — never f-string interpolation — to prevent SQL injection.**
- Update `count_conversations()` (line 330): add `user_id: str | None = None` parameter. Same conditional WHERE clause with bound parameter `:user_id`.

**File: `src/agent_gateway/persistence/null.py`**
- Add matching `user_id: str | None = None` parameter to `list_conversations_summary()` and `count_conversations()` null implementations (parameter is accepted but ignored, matching the existing null-backend pattern).

#### Phase 3: Route-Level Access Control

**File: `src/agent_gateway/dashboard/router.py`**

*Analytics page* (line ~1538):
- Change `current_user: DashboardUser = Depends(get_dashboard_user)` to `current_user: DashboardUser = Depends(require_admin)`

*Executions page* (line ~621):
- Change `current_user: DashboardUser = Depends(get_dashboard_user)` to `current_user: DashboardUser = Depends(require_admin)`

*Execution detail page* — also restrict to admin (look for the `/executions/{execution_id}` route):
- Change dependency to `require_admin`

*Conversations page* (line ~859):
- Keep `get_dashboard_user` dependency
- Pass `user_id=current_user.username` to `repo.list_conversations_summary()` and `repo.count_conversations()` when `not current_user.is_admin`
- Admin users see all conversations (pass `user_id=None`)

*Conversation detail page* (line ~892):
- For non-admin users, after fetching records via `list_by_session`, **filter the results** to only include records where `user_id` matches `current_user.username`: `records = [r for r in records if r.user_id == current_user.username]`. If the filtered list is empty, raise `HTTPException(status_code=404)` (don't leak existence of other users' conversations). This prevents cross-user data leakage in shared sessions — without filtering, a user who owns one execution in a session could see all other users' executions in that session.
- **NULL `user_id` handling**: Rows with `NULL user_id` (pre-migration data or scheduler-initiated executions) are visible only to admin users, both at the list level (the `AND user_id = :user_id` WHERE clause naturally excludes NULL rows for non-admin queries) and at the detail level (the ownership filter will exclude them since `None != current_user.username`). This is the correct behavior — admins see everything, regular users see only their own data.

#### Phase 4: Sidebar Conditional Rendering

**File: `src/agent_gateway/dashboard/templates/dashboard/base.html`**

The `current_user` template variable is already available (passed in all route contexts). Wrap admin-only nav links in Jinja2 conditionals:

```html
{% if current_user and current_user.is_admin %}
<a href="/dashboard/executions" ...>
  ...Executions...
</a>
{% endif %}

{% if current_user and current_user.is_admin %}
<a href="/dashboard/analytics" ...>
  ...Analytics...
</a>
{% endif %}

{% if current_user and current_user.is_admin %}
<a href="/dashboard/schedules" ...>
  ...Schedules...
</a>
{% endif %}
```

The Conversations link remains visible to all users. Agents, Notifications, and Chat links remain visible to all users. The Schedules link is hidden for non-admin users because the schedules management routes already use `require_admin` — hiding the sidebar link keeps the UI consistent with the access control.

#### Phase 5: Example Project Update

**File: `examples/test-project/app.py`**

The example project already configures both admin and regular user credentials in the `use_dashboard()` call (lines 112-123). Add a comment block above the `else` branch explaining expected behavior for each role:

```python
# Dashboard role-based access:
#   Admin user (admin/adminpass):
#     - Full access to all pages: Agents, Executions, Analytics, Conversations, Schedules
#     - Conversations page shows ALL conversations including those with no user_id
#   Regular user (user/userpass):
#     - Can access: Agents, Conversations, Notifications, Chat
#     - Cannot access: Executions, Analytics, Schedules (redirected to Agents page)
#     - Conversations page shows only their own conversations
```

No credential changes needed — the existing `admin_username="admin"` / `admin_password="adminpass"` and `auth_username="user"` / `auth_password="userpass"` are already correctly configured.

## Acceptance Criteria

- [x] Gateway fails to start with `ConfigError` if dashboard password auth is enabled but `admin_username` or `admin_password` is missing
- [x] Gateway starts normally with OAuth2 dashboard auth even without `admin_username`/`admin_password`
- [x] `AdminRequiredError` subclasses `AgentGatewayError`
- [x] Analytics page returns 303 redirect to `/dashboard/agents` for non-admin users
- [x] Executions page returns 303 redirect to `/dashboard/agents` for non-admin users
- [x] Execution detail page returns 303 redirect for non-admin users
- [x] Conversations page shows only current user's conversations for non-admin users
- [x] Conversations page shows all conversations for admin users
- [x] Rows with NULL `user_id` (pre-migration) are visible only to admin users at both list and detail levels
- [x] Conversation detail page returns 404 for non-admin users accessing another user's conversation
- [x] Sidebar hides Executions, Analytics, and Schedules links for non-admin users
- [x] Sidebar shows Conversations link for all users
- [x] New `user_id` column on `executions` table with migration `011`
- [x] `user_id` is populated when executions are created via authenticated API calls (in `invoke.py`)
- [x] Scheduler-initiated executions have `user_id=None`
- [x] HTMX requests to admin-only pages return 403 with `HX-Reswap: none` for non-admin users (existing `require_admin` behavior)
- [x] SQL queries use bound parameters (`:user_id`) for the user_id filter, never f-string interpolation

## Testing Strategy

**File: `tests/test_integration/test_dashboard_role_access.py`** (new)

Test cases using the existing pattern from `test_dashboard_filters.py` (SQLite backend, `httpx.AsyncClient` + `ASGITransport`):

1. **Admin can access analytics page** — login as admin, GET `/dashboard/analytics`, assert 200
2. **Non-admin redirected from analytics** — login as regular user, GET `/dashboard/analytics`, assert 303 to `/dashboard/agents`
3. **Admin can access executions page** — similar
4. **Non-admin redirected from executions** — similar
5. **Non-admin sees only own conversations** — seed executions with different `user_id` values, login as regular user, verify only matching conversations appear
6. **Admin sees all conversations** — same seed, login as admin, verify all appear
7. **Non-admin cannot view another user's conversation detail** — assert 404
8. **HTMX request to admin page by non-admin** — assert 403 with `HX-Reswap` header
9. **Startup fails without admin credentials (password auth)** — create a Gateway with `use_dashboard(auth_username="u", auth_password="p")` but no `admin_username`/`admin_password`, trigger startup, assert `ConfigError` is raised
10. **Startup succeeds with OAuth2 auth without admin credentials** — create a Gateway with `use_dashboard(oauth2_issuer=..., oauth2_client_id=...)` but no `admin_username`/`admin_password`, trigger startup, assert no error
10. **Pagination total_pages correct for non-admin** — seed 15 executions (10 for user-A, 5 for user-B) with page size 5. Login as user-A, verify `total_pages=2`. Login as user-B, verify `total_pages=1`.

**File: `tests/test_integration/test_dashboard_filters.py`** — may need minor updates if execution seeding changes

**Migration test**: Add test for the new migration `011` in the existing migration test file pattern.

## Documentation Updates

- **`docs/guides/dashboard.md`** (or equivalent): Document role-based access, which pages are admin-only, and that `admin_username`/`admin_password` are required when dashboard auth is enabled
- **`docs/llms.txt`**: Update with dashboard access control info
- **`docs/api-reference/configuration.md`**: Note that `admin_username`/`admin_password` controls page visibility and is mandatory

## Dependencies & Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Existing executions have no `user_id` | Old conversations won't be filterable for non-admin users | Rows with `NULL user_id` are shown to admin only. The SQL `AND user_id = :user_id` clause naturally excludes NULL rows. |
| Session-based conversation page uses `session_id` grouping from executions, not the `conversations` table | The `user_id` filter must be added to the executions-based query, not the conversations table | Add `user_id` to `executions` table |
| `invoke()` may not always have auth context | Some invocations (schedule, internal) won't have a user_id | `user_id` is nullable — these remain visible only to admin |
| `delegate_to` child executions | Delegated executions are created internally without auth context | Out of scope — will be planned separately |
| Existing dashboards without admin credentials | Gateway will refuse to start after this change | `ConfigError` message is clear and actionable |

## Verification Checklist

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest -m "not e2e" -x -q
```

## References

- Auth: `src/agent_gateway/dashboard/auth.py` — `DashboardUser.is_admin`, `make_require_admin()`, `AdminRequiredError` (line 14)
- Router: `src/agent_gateway/dashboard/router.py` — all route definitions
- Sidebar: `src/agent_gateway/dashboard/templates/dashboard/base.html` lines 93-128
- Executions schema: `src/agent_gateway/persistence/backends/sql/base.py` lines 76-101
- Conversations query: `src/agent_gateway/persistence/backends/sql/repository.py` lines 301-339
- Existing admin-required handler: `src/agent_gateway/dashboard/router.py` line 109 — redirects to `/dashboard/agents`
- Invoke ExecutionRecord creation: `src/agent_gateway/api/routes/invoke.py` lines 167-177 (primary site), auth derivation at lines 220-221
- Scheduler ExecutionRecord creation: `src/agent_gateway/scheduler/engine.py` lines 320 and 422
- Null repository: `src/agent_gateway/persistence/null.py`
- Protocols: `src/agent_gateway/persistence/protocols.py`
- SQL repository: `src/agent_gateway/persistence/backends/sql/repository.py`
- Exceptions: `src/agent_gateway/exceptions.py` — `ConfigError`, `AgentGatewayError`
- Test pattern: `tests/test_integration/test_dashboard_filters.py`
- Latest migration: `src/agent_gateway/persistence/migrations/versions/010_add_schedule_source_column.py`
