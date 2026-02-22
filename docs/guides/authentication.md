# Authentication

Agent Gateway supports multiple authentication modes: API key, OAuth2/JWT, composite (try multiple providers), and custom. All modes use the `Authorization: Bearer <token>` header. Authentication can be configured in `gateway.yaml` or programmatically via the `gw` fluent API.

## API key authentication

The default mode. Clients send a static API key as a Bearer token.

### Configure in gateway.yaml

```yaml
auth:
  enabled: true
  mode: api_key
  api_keys:
    - name: frontend-service
      key: "${FRONTEND_API_KEY}"
      scopes: ["*"]
    - name: read-only-client
      key: "${READONLY_API_KEY}"
      scopes: ["agents:read"]
```

### Configure in code

```python
from agent_gateway import Gateway

gw = Gateway(workspace="./workspace")

gw.use_api_keys([
    {
        "name": "frontend-service",
        "key": "sk-my-secret-key",
        "scopes": ["*"],
    },
    {
        "name": "read-only-client",
        "key": "sk-readonly-key",
        "scopes": ["agents:read"],
    },
])
```

### Key configuration

| Field | Required | Description |
|---|---|---|
| `name` | yes | Identifying label for the key (becomes the auth subject) |
| `key` | yes | The plaintext API key |
| `scopes` | no | List of scopes granted by this key. Defaults to `["*"]` (full access) |

### Security details

- Keys are hashed with SHA-256 on startup. Plaintext keys are never stored in memory.
- Comparisons use `hmac.compare_digest` to prevent timing attacks.
- Keys support expiration (`expires_at`) and revocation (`revoked`) when managed programmatically.

### Usage

```
Authorization: Bearer sk-my-secret-key
```

## OAuth2 / JWT authentication

Validates JWT access tokens against an OAuth2 or OIDC provider's JWKS endpoint. Requires the `oauth2` extra:

```
pip install agents-gateway[oauth2]
```

### Configure in gateway.yaml

```yaml
auth:
  enabled: true
  mode: oauth2
  oauth2:
    issuer: "https://auth.example.com"
    audience: "my-api"
    jwks_uri: null               # Auto-derived: <issuer>/.well-known/jwks.json
    algorithms: [RS256, ES256]   # Allowed signing algorithms
    scope_claim: "scope"         # Claim name for scopes (use "scp" for Azure AD)
    clock_skew_seconds: 30       # Tolerance for clock drift
```

### Configure in code

```python
gw.use_oauth2(
    issuer="https://auth.example.com",
    audience="my-api",
    # jwks_uri="https://auth.example.com/.well-known/jwks.json",  # auto-derived
    # algorithms=["RS256", "ES256"],
    # scope_claim="scope",
    # clock_skew_seconds=30,
)
```

### Configuration fields

| Field | Default | Description |
|---|---|---|
| `issuer` | required | OIDC issuer URL. Used to derive `jwks_uri` and validate the `iss` claim |
| `audience` | required | Expected `aud` claim value |
| `jwks_uri` | auto-derived | JWKS endpoint URL. Defaults to `<issuer>/.well-known/jwks.json` |
| `algorithms` | `[RS256, ES256]` | Allowed JWT signing algorithms |
| `scope_claim` | `scope` | JWT claim that contains scopes. Use `scp` for Azure AD |
| `clock_skew_seconds` | `30` | Seconds of tolerance for `exp`/`nbf` validation |

### Security details

- Only asymmetric algorithms are permitted: `RS256`, `RS384`, `RS512`, `ES256`, `ES384`, `ES512`. Symmetric algorithms (`HS*`) and `none` are rejected.
- JWKS keys are cached for one hour. The cache is refreshed automatically when a token presents an unknown `kid` (handles key rotation without downtime).
- When the JWKS endpoint is unreachable, the provider falls back to the stale cache if available.
- The `exp`, `iss`, and `aud` claims are always required.

### Usage

Pass the access token from your OAuth2 authorization server:

```
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

## Composite authentication

Try multiple providers in sequence. The first successful authentication wins.

### Configure in gateway.yaml

```yaml
auth:
  enabled: true
  mode: composite
  api_keys:
    - name: service-account
      key: "${SERVICE_ACCOUNT_KEY}"
      scopes: ["*"]
  oauth2:
    issuer: "https://auth.example.com"
    audience: "my-api"
```

### Configure in code

```python
from agent_gateway.auth.providers.api_key import ApiKeyProvider
from agent_gateway.auth.providers.oauth2 import OAuth2Provider
from agent_gateway.auth.providers.composite import CompositeProvider
from agent_gateway.auth.domain import ApiKeyRecord

gw.use_auth_provider(
    CompositeProvider([
        ApiKeyProvider([ApiKeyRecord(...)]),
        OAuth2Provider(issuer="...", audience="..."),
    ])
)
```

Providers are tried in the order given. The first to return a successful `AuthResult` is used. All providers must fail for the request to be rejected.

## Custom authentication

Implement the `AuthProvider` protocol to plug in any authentication mechanism:

```python
from agent_gateway.auth.protocols import AuthProvider
from agent_gateway.auth.domain import AuthResult

class MyAuthProvider:
    async def authenticate(self, token: str) -> AuthResult:
        # Validate the token using your own logic
        if token == "valid-token":
            return AuthResult.ok(
                subject="user-123",
                scopes=["*"],
                method="custom",
            )
        return AuthResult.denied("Invalid token")

    async def close(self) -> None:
        # Release resources (HTTP clients, DB connections, etc.)
        pass

gw.use_auth_provider(MyAuthProvider())
```

### AuthProvider protocol

```python
class AuthProvider(Protocol):
    async def authenticate(self, token: str) -> AuthResult: ...
    async def close(self) -> None: ...
```

### AuthResult

`AuthResult` is the return type from all auth providers:

| Field | Type | Description |
|---|---|---|
| `authenticated` | `bool` | Whether authentication succeeded |
| `subject` | `str` | Authenticated identity (user ID, service name, etc.) |
| `scopes` | `list[str]` | Scopes granted to this identity |
| `auth_method` | `str` | Method used: `api_key`, `oauth2`, `custom` |
| `claims` | `dict` | Additional claims (e.g. JWT payload fields) |
| `error` | `str` | Reason for failure (when `authenticated=False`) |

Convenience constructors:

```python
# Success
AuthResult.ok(subject="alice", scopes=["*"], method="custom")

# Failure
AuthResult.denied("Token has expired")
```

## Scopes

Scopes control what an authenticated client is allowed to do. Use `"*"` to grant full access. Specific scope strings are compared literally against the scopes required by the requested operation.

```yaml
api_keys:
  - name: full-access
    key: "${FULL_KEY}"
    scopes: ["*"]
  - name: read-only
    key: "${READONLY_KEY}"
    scopes: ["agents:read", "executions:read"]
```

## Public paths

Some paths bypass authentication entirely. The health check endpoint is public by default:

```yaml
auth:
  public_paths:
    - /v1/health
    - /metrics
```

Paths are matched as exact strings. All other paths require a valid token when auth is enabled.

## Disabling authentication

For development or internal services, authentication can be disabled entirely:

### In code

```python
gw = Gateway(workspace="./workspace", auth=False)
```

### In gateway.yaml

```yaml
auth:
  enabled: false
```

Or set `mode: none`:

```yaml
auth:
  mode: none
```

All three approaches have the same effect — every request is accepted without a token.
