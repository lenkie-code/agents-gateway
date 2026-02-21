---
title: "Dashboard UI Refresh, OAuth2 Login & Color Theming"
type: feat
status: active
date: 2026-02-21
---

# Dashboard UI Refresh, OAuth2 Login & Color Theming

## Overview

Iterate on the built-in dashboard with three improvements: a modern minimal design refresh (Linear/Vercel aesthetic), OAuth2/OIDC login as an alternative to username/password (mutually exclusive — operator picks one), and extended white-label color theming with semantic color tokens (primary, secondary, accent, surface, sidebar).

## Problem Statement / Motivation

1. **Design**: The current dashboard is functional but visually plain. A modern minimal aesthetic improves perceived quality and makes white-labelling more appealing.
2. **Auth**: Dashboard login only supports a single hardcoded username/password. Organizations using SSO (Okta, Auth0, Azure AD, Google) cannot use their existing identity provider for dashboard access.
3. **Theming**: White-label only exposes `accent_color` and `accent_color_dark`. Operators wanting to brand the dashboard to their product have no control over surface colors, sidebar, or secondary accent.

## Proposed Solution

### A. Design Refresh

Rework `tokens.css` and `app.css` for a modern minimal look:

- **Tighter spacing**, subtle borders (1px `border-color` tokens), less visual weight
- **Cleaner cards**: no heavy shadows, use border + subtle background lift
- **Typography**: keep Inter, refine heading weights and sizes
- **Sidebar**: cleaner nav items, subtle active indicator (left bar or background tint)
- **Tables/lists**: lighter row separators, more breathing room
- **Buttons**: flat primary with hover lift, ghost/outline secondary
- **Chat**: cleaner message bubbles, better timestamp/meta positioning
- **Login page**: centered card, minimal branding area
- **Dark mode**: ensure all refreshed tokens have dark variants

Reference style: Linear app sidebar + Vercel dashboard content area.

No template structure changes — only CSS token values and component styles.

### B. OAuth2 Dashboard Login (OIDC Discovery)

Add OAuth2 Authorization Code flow as a **mutually exclusive** alternative to username/password. Since the dashboard is a server-side rendered app, this uses a **confidential client** (client_secret is required, no public client / PKCE-only mode).

Only one auth method is active at a time:
- If `oauth2` is configured → OAuth2 login, username/password fields ignored
- If `oauth2` is not configured → username/password login (existing behavior)
- Validation at startup: error if both `password` and `oauth2.issuer` are set

#### Configuration

Extend `DashboardAuthConfig` in `config.py`:

```python
class DashboardOAuth2Config(BaseModel):
    issuer: str = ""            # OIDC issuer URL
    client_id: str = ""
    client_secret: str = ""     # Required — confidential client
    scopes: list[str] = ["openid", "profile", "email"]
    # Auto-discovered from .well-known/openid-configuration:
    # authorization_endpoint, token_endpoint, userinfo_endpoint, jwks_uri

class DashboardAuthConfig(BaseModel):
    enabled: bool = True
    # Option A: username/password (default)
    username: str = "admin"
    password: str = ""
    # Option B: OAuth2/OIDC (mutually exclusive with username/password)
    oauth2: DashboardOAuth2Config | None = None
    session_secret: str = ""
```

Fluent API — operator chooses one:

```python
# Option A: username/password (existing)
gw.use_dashboard(
    auth_username="admin",
    auth_password="secret",
)

# Option B: OAuth2/OIDC (confidential client)
gw.use_dashboard(
    oauth2_issuer="https://accounts.google.com",
    oauth2_client_id="xxx.apps.googleusercontent.com",
    oauth2_client_secret="GOCSPX-xxx",
)
```

`gateway.yaml` — one or the other:

```yaml
# Option A: username/password
dashboard:
  enabled: true
  auth:
    username: admin
    password: ${DASHBOARD_PASSWORD}

# Option B: OAuth2/OIDC
dashboard:
  enabled: true
  auth:
    oauth2:
      issuer: https://accounts.google.com
      client_id: ${OAUTH2_CLIENT_ID}
      client_secret: ${OAUTH2_CLIENT_SECRET}
```

#### OIDC Discovery

On startup (or first request), fetch `{issuer}/.well-known/openid-configuration` to get:
- `authorization_endpoint`
- `token_endpoint`
- `userinfo_endpoint`
- `jwks_uri`

Cache the discovery document with a TTL (e.g. 1 hour). Use `httpx.AsyncClient`.

#### Routes

Add to the dashboard public router:

| Route | Method | Purpose |
|---|---|---|
| `GET /dashboard/oauth2/authorize` | GET | Generate state + PKCE verifier, store in session, redirect to IdP |
| `GET /dashboard/oauth2/callback` | GET | Validate state, exchange code for tokens, create session |

#### Authorization Flow

1. User navigates to `/dashboard/login` — page shows only the "Sign in with SSO" button (no username/password form)
2. User clicks button → `GET /dashboard/oauth2/authorize`:
   - Generate `state` (random 32 bytes, hex)
   - Store `state` in session
   - Redirect to `authorization_endpoint` with params: `response_type=code`, `client_id`, `redirect_uri=/dashboard/oauth2/callback`, `scope`, `state`
   - Client authenticates via `client_secret` during token exchange (confidential client — no PKCE needed)
3. User authenticates at IdP, consents, redirects back
4. `GET /dashboard/oauth2/callback`:
   - Validate `state` matches session
   - Exchange `code` for tokens at `token_endpoint` (POST with `grant_type=authorization_code`, `code`, `redirect_uri`, `client_id`, `client_secret`)
   - Validate the `id_token` JWT: signature (from JWKS), `iss`, `aud`, `exp`
   - Extract `sub`, `email`, `name` from ID token or userinfo endpoint
   - **Tokens never sent to the browser** — discard `access_token` and `id_token` after extracting user info. The only browser-facing credential is the session cookie.
   - Create `DashboardUser(username=email or sub, display_name=name, auth_method="oauth2")`
   - Store user info (not tokens) in session cookie, redirect to `/dashboard/`

#### DashboardUser Extension

```python
@dataclass
class DashboardUser:
    username: str
    display_name: str = ""
    auth_method: str = "password"  # "password" or "oauth2"
```

#### Login Page Changes

The login page renders one of two forms based on the configured auth method:

**When OAuth2 is configured:**

```
┌──────────────────────────────┐
│         [Logo]               │
│      Dashboard Title         │
│                              │
│  ┌────────────────────────┐  │
│  │  Sign in with SSO  →   │  │
│  └────────────────────────┘  │
│                              │
└──────────────────────────────┘
```

**When username/password is configured (default):**

```
┌──────────────────────────────┐
│         [Logo]               │
│      Dashboard Title         │
│                              │
│  Username: [____________]    │
│  Password: [____________]    │
│  [       Sign In       ]     │
│                              │
└──────────────────────────────┘
```

No mixed mode — the template checks which auth method is active.

#### Error Handling

- IdP unreachable → flash error "SSO provider unavailable, please try again"
- State mismatch → redirect to login with flash "Authentication failed, please try again"
- Token validation failure → redirect to login with flash "Authentication failed"
- All errors logged at WARNING level

#### Security

- **Confidential client**: `client_secret` sent during token exchange (server-side only, never exposed to browser)
- **No tokens in browser**: `access_token`, `id_token`, and `refresh_token` are never sent to or stored in the browser. They are used server-side during the callback to extract user identity, then discarded. The session cookie (signed by Starlette `SessionMiddleware`) is the sole browser credential.
- `state` parameter validated (CSRF protection)
- ID token signature verified against JWKS
- `iss` and `aud` claims validated
- Session cookie: `same_site="lax"`, `httponly=True`, `secure` in production
- Startup validation: error if `client_secret` is empty when OAuth2 is configured

### C. Semantic Color Theming

#### New Config

```python
class DashboardThemeConfig(BaseModel):
    mode: Literal["light", "dark", "auto"] = "auto"
    colors: DashboardColorConfig = DashboardColorConfig()

class DashboardColorConfig(BaseModel):
    primary: str = "#6366f1"        # Main brand color (buttons, links, active states)
    primary_dark: str = "#818cf8"   # Primary in dark mode
    secondary: str = "#64748b"      # Secondary actions, muted text
    secondary_dark: str = "#94a3b8"
    accent: str = "#6366f1"         # Highlight/accent (defaults to primary)
    accent_dark: str = "#818cf8"
    surface: str = "#ffffff"        # Card/panel backgrounds
    surface_dark: str = "#1e293b"
    sidebar: str = "#0f172a"        # Sidebar background
    sidebar_dark: str = "#020617"
    danger: str = "#ef4444"         # Error/destructive actions
    danger_dark: str = "#f87171"
```

Fluent API:

```python
gw.use_dashboard(
    theme="dark",
    primary_color="#2563eb",
    secondary_color="#64748b",
    surface_color="#ffffff",
    sidebar_color="#0f172a",
)
```

Each color gets a `_dark` variant. If operator doesn't provide `_dark`, auto-derive by lightening 10-15%.

#### CSS Integration

Inject all semantic tokens as CSS custom properties in `base.html` and `login.html`:

```html
<style>
  :root {
    --color-primary: {{ colors.primary }};
    --color-secondary: {{ colors.secondary }};
    --color-accent: {{ colors.accent }};
    --color-surface: {{ colors.surface }};
    --color-sidebar-bg: {{ colors.sidebar }};
    --color-danger: {{ colors.danger }};
  }
  html.dark, :root:not(.light) { /* dark overrides */ }
</style>
```

Update `tokens.css` to reference these instead of hardcoded values:
- `--color-accent-text` → `var(--color-primary)`
- `--color-bg` → derives from `--color-surface`
- `--sidebar-bg` → `var(--color-sidebar-bg)`
- etc.

#### Backward Compatibility

`accent_color` and `accent_color_dark` from the old config map to `colors.primary` and `colors.primary_dark`. If operator only sets `accent_color`, it populates `primary` (and `accent` defaults to `primary`). No breaking change.

#### Validation

- Validate color strings with regex: `^#[0-9a-fA-F]{3,8}$` or named CSS colors
- Log a warning (not error) if contrast ratio between text and background is below 4.5:1

## Technical Considerations

### Architecture

- OAuth2 OIDC client is dashboard-specific (not shared with API auth middleware)
- Confidential client: `client_secret` used for token exchange (server-side, never exposed to browser)
- Discovery document cached in-memory with TTL refresh
- Dependency: `httpx` (already in deps for OAuth2Provider JWKS fetching), `PyJWT` (already in oauth2 extra)
- Auth methods are mutually exclusive — no mixed login page complexity

### Ordering

1. **Design refresh first** → establishes the CSS token set
2. **Color theming second** → builds on the refreshed tokens
3. **OAuth2 third** → independent of visual changes, login page template already updated in step 1

### Testing

- OAuth2 flow: mock the OIDC discovery and token exchange endpoints
- Color theming: unit test config parsing, validate CSS injection in template rendering
- Design: visual inspection (no automated visual regression tests)

## Acceptance Criteria

### Design Refresh
- [ ] Updated `tokens.css` with refined spacing, shadows, borders
- [ ] Updated `app.css` with modern minimal component styles
- [ ] All pages (agents, executions, execution detail, chat, analytics, login) refreshed
- [ ] Dark mode works correctly with all changes
- [ ] HTMX partials render consistently with full-page loads
- [ ] No template structure changes (only CSS)

### OAuth2 Login
- [ ] `DashboardOAuth2Config` model in `config.py` with required `client_secret` (confidential client)
- [ ] Startup validation: error if both password and oauth2 are configured
- [ ] Startup validation: error if oauth2 is configured without `client_secret`
- [ ] OIDC discovery client with caching
- [ ] `/dashboard/oauth2/authorize` route with state parameter
- [ ] `/dashboard/oauth2/callback` route with confidential client token exchange + ID token validation
- [ ] Login page shows SSO button (only) when OAuth2 is the auth method
- [ ] Login page shows username/password form (only) when password is the auth method
- [ ] `DashboardUser` extended with `display_name` and `auth_method`
- [ ] `use_dashboard()` fluent API accepts `oauth2_issuer`, `oauth2_client_id`, `oauth2_client_secret`
- [ ] `gateway.yaml` supports `dashboard.auth.oauth2` section
- [ ] Error handling for all OAuth2 failure modes
- [ ] Unit tests with mocked OIDC endpoints
- [ ] Example project updated to show OAuth2 config (commented out, with instructions)

### Color Theming
- [ ] `DashboardColorConfig` model with primary, secondary, accent, surface, sidebar, danger
- [ ] Each color has `_dark` variant (auto-derived if not set)
- [ ] CSS custom properties injected in templates
- [ ] `tokens.css` references injected properties (no hardcoded brand colors)
- [ ] `use_dashboard()` accepts `primary_color`, `secondary_color`, `surface_color`, `sidebar_color`
- [ ] `gateway.yaml` supports `dashboard.theme.colors` section
- [ ] Backward compatible with existing `accent_color` config
- [ ] Color format validation
- [ ] Example project updated to demonstrate custom colors

## Dependencies & Risks

- **httpx** already a dependency (used by OAuth2Provider) — no new deps
- **Risk**: OIDC providers have quirks (Azure AD returns `scp` not `scope`, Google requires `access_type=offline` for refresh tokens). Mitigation: test against at least Google and a generic OIDC provider (Keycloak/Auth0).
- **Risk**: Design refresh is subjective. Mitigation: keep changes incremental, don't restructure templates.
- **Risk**: Color theming could produce unreadable combinations. Mitigation: log contrast warnings, document recommended palettes.

## Files to Create/Modify

### New Files
- `src/agent_gateway/dashboard/oauth2.py` — OIDC discovery client, authorize/callback handlers

### Modified Files
- `src/agent_gateway/config.py` — `DashboardOAuth2Config`, `DashboardColorConfig`, updated `DashboardThemeConfig`
- `src/agent_gateway/gateway.py` — `use_dashboard()` fluent API extensions, OAuth2 route registration
- `src/agent_gateway/dashboard/router.py` — mount OAuth2 routes
- `src/agent_gateway/dashboard/auth.py` — extended `DashboardUser`, login page context
- `src/agent_gateway/dashboard/models.py` — if view models need color/auth context
- `src/agent_gateway/dashboard/static/dashboard/tokens.css` — design refresh + semantic color vars
- `src/agent_gateway/dashboard/static/dashboard/app.css` — component style refresh
- `src/agent_gateway/dashboard/templates/dashboard/base.html` — color injection, minor layout tweaks
- `src/agent_gateway/dashboard/templates/dashboard/login.html` — OAuth2 SSO button, dual auth layout
- `examples/test-project/app.py` — demonstrate color theming + OAuth2 config

### Test Files
- `tests/test_dashboard/test_oauth2.py` — OIDC flow tests
- `tests/test_dashboard/test_theming.py` — color config and CSS injection tests

## References

- Existing OAuth2Provider: `src/agent_gateway/auth/providers/oauth2.py`
- Current dashboard auth: `src/agent_gateway/dashboard/auth.py`
- Current theme config: `src/agent_gateway/config.py:189-208`
- CSS tokens: `src/agent_gateway/dashboard/static/dashboard/tokens.css`
- OIDC Discovery spec: https://openid.net/specs/openid-connect-discovery-1_0.html
- PKCE spec: https://www.rfc-editor.org/rfc/rfc7636
