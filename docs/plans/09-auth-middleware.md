---
title: "Phase 2.1: Authentication Middleware"
type: feat
status: pending
date: 2026-02-18
depends_on: [08]
blocks: []
parent: 2026-02-18-feat-agent-gateway-framework-plan.md
---

# Phase 2.1: Authentication Middleware

## Goal

API key authentication for `/v1/` routes with scope-based access control. Custom routes are unaffected. After this phase, agent endpoints require a valid API key with appropriate scopes.

## Prerequisites

- Phase 08 (Gateway + API routes working)

---

## Tasks

### 1. Pure ASGI Auth Middleware

**File:** `src/agent_gateway/api/middleware/auth.py`

MUST be pure ASGI (NOT `BaseHTTPMiddleware`):

```python
class AuthMiddleware:
    def __init__(self, app: ASGIApp, config: AuthConfig):
        self.app = app
        self.config = config
        self._keys = {k.key: k for k in config.api_keys}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/v1/"):
            # Custom routes — no auth
            await self.app(scope, receive, send)
            return

        # Extract Bearer token from headers
        # Validate against configured keys
        # Check scopes for the requested endpoint
        # 401 if no/invalid key, 403 if wrong scope
```

### 2. Scope Checking

Map endpoints to required scopes:
- `POST /v1/agents/*/invoke` → `agents:invoke` or `agents:invoke:{agent_id}`
- `GET /v1/executions/*` → `executions:read`
- `POST /v1/executions/*/cancel` → `executions:cancel`
- `GET /v1/schedules/*` → `schedules:read`
- `POST /v1/schedules/*/run|pause|resume` → `schedules:manage`
- `POST /v1/reload` → `admin`
- `*` scope grants everything

### 3. Custom Auth Support

`Gateway(auth=my_async_fn)` — user provides their own auth function:

```python
async def my_auth(request: Request) -> AuthResult:
    return AuthResult(authenticated=True, identity="user@example.com", scopes=["*"])
```

### 4. Disable Auth

`Gateway(auth=False)` or `auth.mode: none` in gateway.yaml → no middleware added.

### 5. Env Var Resolution in API Keys

Keys in gateway.yaml use `${VAR}` syntax — resolve from environment at startup.

---

## Tests

- Valid key → 200
- Invalid key → 401
- Wrong scope → 403
- No auth header → 401
- `auth=False` → no auth enforced
- Custom auth function
- Custom routes unaffected by auth
- `*` scope grants everything
- Agent-specific scope: `agents:invoke:underwriting`

## Acceptance Criteria

- [ ] `/v1/` routes require valid API key
- [ ] Scopes enforced per endpoint
- [ ] Custom routes bypass auth
- [ ] Custom auth function works
- [ ] Auth can be disabled
- [ ] Pure ASGI middleware (no BaseHTTPMiddleware)
