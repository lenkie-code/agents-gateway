# CORS

Cross-Origin Resource Sharing (CORS) must be configured when browser-based clients — single-page applications, embedded chatbots, or the Agent Gateway dashboard itself — call your API from a different origin. Without it, browsers block these requests.

Agent Gateway uses Starlette's `CORSMiddleware` under the hood.

## Configuration via `gateway.yaml`

```yaml
cors:
  enabled: true
  allow_origins:
    - "https://myapp.com"
    - "https://admin.myapp.com"
  allow_methods:
    - "GET"
    - "POST"
    - "DELETE"
    - "OPTIONS"
  allow_headers:
    - "Authorization"
    - "Content-Type"
  allow_credentials: false
  max_age: 3600
```

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Master switch. Set to `true` to activate CORS middleware. |
| `allow_origins` | `[]` | List of allowed origin URLs. Use `["*"]` to allow all origins (not compatible with `allow_credentials: true`). |
| `allow_methods` | `["GET"]` | HTTP methods to allow in cross-origin requests. |
| `allow_headers` | `[]` | Request headers browsers are permitted to send. |
| `allow_credentials` | `false` | Whether to allow cookies and `Authorization` headers in cross-origin requests. |
| `max_age` | `600` | How long (in seconds) browsers may cache preflight responses. |

## Fluent API

You can configure CORS directly on the gateway instance instead of (or in addition to) `gateway.yaml`:

```python
from agent_gateway import Gateway

gw = Gateway()
gw.use_cors(
    allow_origins=["https://myapp.com"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
    max_age=3600,
)
```

Values provided via the fluent API take precedence over anything set in `gateway.yaml`.

## Validation

Setting `allow_credentials=True` while also including `"*"` in `allow_origins` is invalid per the CORS specification — browsers reject such responses. Agent Gateway enforces this at configuration time and raises a `ValueError` if the combination is detected, whether configured via `gateway.yaml` or the fluent API:

```python
# Raises ValueError: allow_credentials=True is not compatible with allow_origins=["*"]
gw.use_cors(allow_origins=["*"], allow_credentials=True)
```

## Common Patterns

### Development — allow all origins

During local development it is often convenient to allow all origins without credentials:

```yaml
cors:
  enabled: true
  allow_origins: ["*"]
  allow_methods: ["*"]
  allow_headers: ["*"]
  allow_credentials: false
```

### Production SPA with authentication

Allow a specific origin and permit the `Authorization` header for token-based auth:

```python
gw.use_cors(
    allow_origins=["https://myapp.com"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
    max_age=86400,
)
```

### Cookie-based session auth

If your SPA authenticates via cookies rather than bearer tokens, enable credentials and list origins explicitly:

```yaml
cors:
  enabled: true
  allow_origins:
    - "https://myapp.com"
  allow_methods: ["GET", "POST", "OPTIONS"]
  allow_headers: ["Content-Type"]
  allow_credentials: true
  max_age: 3600
```
