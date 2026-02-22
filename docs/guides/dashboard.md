# Dashboard

Agent Gateway ships with a built-in web dashboard for monitoring agents, browsing execution history, reviewing conversations, and chatting with agents directly from the browser. It is powered by HTMX for lightweight partial page updates without a separate frontend build step.

## Enabling the Dashboard

### Via `gateway.yaml`

```yaml
dashboard:
  enabled: true
```

### Via the fluent API

```python
from agent_gateway import Gateway

gw = Gateway()
gw.use_dashboard()
```

The dashboard is mounted at `/dashboard`. Once enabled, open that path in your browser while your service is running.

## Pages

| Page | Path | Description |
|---|---|---|
| Agents overview | `/dashboard/agents` | List of all registered agents with status and metadata. |
| Executions | `/dashboard/executions` | Filterable list of past executions. Filter by `agent_id`, `status`, or `session_id`. |
| Execution detail | `/dashboard/executions/{id}` | Full execution record including input, output, tool calls, and the distributed trace. |
| Conversations | `/dashboard/conversations` | List of conversation sessions across all agents. |
| Conversation detail | `/dashboard/conversations/{id}` | Full message history for a session. |
| Interactive chat | `/dashboard/chat` | Send messages to any agent and receive streaming responses over SSE. |
| Schedules | `/dashboard/schedules` | View and manage cron-scheduled agent jobs. |
| Analytics | `/dashboard/analytics` | Cost and execution charts over time. Requires SQL persistence. |

## Authentication

Dashboard authentication is independent of your API authentication configuration. You can secure the dashboard with a username/password form or an OAuth2/OIDC provider regardless of how your API routes are protected.

### Password Authentication

Users log in with a username and password via an HTML form. A session cookie is issued on success and expires after 24 hours.

```python
gw.use_dashboard(
    auth_username="admin",
    auth_password="s3cr3t",
)
```

Or in `gateway.yaml`:

```yaml
dashboard:
  enabled: true
  auth:
    mode: password
    username: admin
    password: s3cr3t
```

### OAuth2 / OIDC

Use the Authorization Code flow with any OIDC-compliant provider (Google, Entra ID, Okta, Keycloak, etc.).

```python
gw.use_dashboard(
    auth_mode="oidc",
    auth_issuer="https://accounts.google.com",
    auth_client_id="your-client-id",
    auth_client_secret="your-client-secret",
)
```

Or in `gateway.yaml`:

```yaml
dashboard:
  enabled: true
  auth:
    mode: oidc
    issuer: "https://accounts.google.com"
    client_id: "your-client-id"
    client_secret: "your-client-secret"
```

## Fluent API Reference

`gw.use_dashboard()` accepts keyword arguments to configure the dashboard inline without a config file:

```python
gw.use_dashboard(
    title="My Agent Service",          # Browser tab title and header text
    logo_url="/static/logo.png",       # URL for the header logo image
    auth_username="admin",             # Password auth username
    auth_password="s3cr3t",            # Password auth password
    auth_mode="oidc",                  # "password" | "oidc" | None
    auth_issuer="https://...",         # OIDC issuer URL
    auth_client_id="...",              # OIDC client ID
    auth_client_secret="...",          # OIDC client secret
    theme="dark",                      # "light" | "dark" | "auto"
    primary_color="#6366f1",           # Primary accent color (hex)
)
```

Fluent API values take precedence over anything set in `gateway.yaml`.

## Theming

The dashboard supports light, dark, and system-preference-aware (`auto`) modes, plus a full set of color overrides. Colors can be specified for both light and dark variants.

```yaml
dashboard:
  enabled: true
  theme:
    mode: auto          # light | dark | auto
    colors:
      primary: "#6366f1"
      primary_dark: "#818cf8"
      secondary: "#64748b"
      secondary_dark: "#94a3b8"
      accent: "#f59e0b"
      accent_dark: "#fbbf24"
      surface: "#ffffff"
      surface_dark: "#1e1e2e"
      sidebar: "#f1f5f9"
      sidebar_dark: "#181825"
      danger: "#ef4444"
      danger_dark: "#f87171"
```

Each `*_dark` variant is applied when the UI is in dark mode.

## Analytics

The analytics page renders cost and execution volume charts over configurable time windows. It requires a SQL persistence backend to be configured — the in-memory default does not support the aggregation queries needed for analytics.

See the [Persistence guide](persistence.md) for details on configuring a SQL backend.
