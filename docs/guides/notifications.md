# Notifications

Agent Gateway can send notifications when an agent run completes, errors, or times out. Two built-in backends are provided: Slack and outbound webhooks. Both can be active simultaneously.

## Events

| Event | When it fires |
|-------|--------------|
| `on_complete` | An agent run finishes successfully |
| `on_error` | An agent run raises an unhandled exception |
| `on_timeout` | An agent run exceeds its configured timeout |

---

## Slack

**Install the extra:**

```bash
pip install agents-gateway[slack]
```

**Configure via `gateway.yaml`:**

```yaml
notifications:
  slack:
    enabled: true
    bot_token: "xoxb-..."
    default_channel: "#alerts"
```

**Or configure fluently in code:**

```python
from agent_gateway import Gateway

gw = Gateway()
gw.use_slack_notifications(
    bot_token="xoxb-...",
    default_channel="#alerts",
)
```

Notifications are sent as [Block Kit](https://api.slack.com/block-kit) rich messages, which include the agent name, event type, execution ID, and a summary of the output or error.

### Custom Slack Templates

Override the message layout with Jinja2 templates. Create `.json.j2` files in a templates directory and point the config at it:

```yaml
notifications:
  slack:
    enabled: true
    bot_token: "xoxb-..."
    default_channel: "#alerts"
    templates_dir: "templates/slack"
```

Template resolution order for a given event:

1. `{templates_dir}/{agent_name}/{event_type}.json.j2` — agent-specific override
2. `{templates_dir}/{event_type}.json.j2` — event-type default
3. Built-in template

Template variables available in every context:

```
agent_name     str    Name of the agent
event          str    "on_complete" | "on_error" | "on_timeout"
execution_id   str    UUID of the execution
session_id     str    Session ID (may be None)
output         any    Agent output (on_complete only)
error          str    Error message (on_error / on_timeout only)
timestamp      str    ISO-8601 timestamp
```

Example template (`on_complete.json.j2`):

```json
[
  {
    "type": "section",
    "text": {
      "type": "mrkdwn",
      "text": "*{{ agent_name }}* finished at {{ timestamp }}\n{{ output | truncate(200) }}"
    }
  }
]
```

---

## Webhooks

**Install the extra:**

```bash
pip install agents-gateway[webhooks]
```

**Configure via `gateway.yaml`:**

```yaml
notifications:
  webhooks:
    - name: "default"
      url: "https://hooks.example.com/agent-events"
      secret: "s3cret"
      events:
        - on_complete
        - on_error
```

**Or configure fluently in code:**

```python
gw.use_webhook_notifications(
    url="https://hooks.example.com/agent-events",
    name="default",
    secret="s3cret",
)
```

Multiple webhooks can be configured; each entry in `notifications.webhooks` is independent.

### Request Signing

Every webhook request is signed with HMAC-SHA256. Two headers are added:

| Header | Value |
|--------|-------|
| `X-AgentGateway-Timestamp` | Unix timestamp (seconds) of the request |
| `X-AgentGateway-Signature` | `sha256("{timestamp}.{body}")` hex digest |

To verify on the receiving end (Python example):

```python
import hashlib, hmac, time

def verify(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        f"{timestamp}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

Reject requests where the timestamp is more than a few minutes old to prevent replay attacks.

### SSRF Protection

Agent Gateway refuses to send webhook requests to private networks, loopback addresses, and cloud metadata endpoints (e.g. `169.254.169.254`). This protection cannot be disabled. If your webhook target resolves to a private IP the request is dropped and an error is logged.

### Custom Webhook Payload

Supply a Jinja2 template string to reshape the payload:

```yaml
notifications:
  webhooks:
    - name: "pagerduty"
      url: "https://events.pagerduty.com/v2/enqueue"
      secret: "s3cret"
      events:
        - on_error
      payload_template: |
        {
          "routing_key": "your-routing-key",
          "event_action": "trigger",
          "payload": {
            "summary": "{{ agent_name }} failed: {{ error }}",
            "severity": "error",
            "source": "agent-gateway"
          }
        }
```

The same template variables listed in the Slack section are available.

---

## Per-Agent Notification Rules

Override which channels receive notifications, and which target within that channel, on a per-agent basis. Add a `notifications` block to the agent's `AGENT.md` frontmatter:

```yaml
---
name: report-agent
notifications:
  on_complete:
    - channel: slack
      target: "#reports"
  on_error:
    - channel: slack
      target: "#alerts"
    - channel: webhook
      target: default
---
```

`target` for Slack is a channel name (with or without `#`). `target` for webhooks is the `name` of the webhook entry in your config.

If no per-agent rules are defined, the gateway-level defaults apply (`default_channel` for Slack, all configured webhooks for webhook events).

---

## Delivery Tracking

When persistence is configured, Agent Gateway automatically records the outcome of every notification dispatch in a `notification_log` table. This works for both direct (in-process) and queue-based delivery paths — no additional configuration is required.

### Delivery record fields

Each record captures:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique delivery record ID |
| `execution_id` | `str` | The execution that triggered the notification |
| `agent_id` | `str` | Agent that produced the event |
| `event_type` | `str` | `on_complete`, `on_error`, or `on_timeout` |
| `channel` | `str` | `slack` or `webhook` |
| `target` | `str` | Slack channel name or webhook name |
| `status` | `str` | `delivered` or `failed` |
| `attempts` | `int` | Number of dispatch attempts made |
| `last_error` | `str \| None` | Error message from the most recent failed attempt |
| `created_at` | `str` | ISO-8601 timestamp when the record was created |
| `delivered_at` | `str \| None` | ISO-8601 timestamp of successful delivery |

### Querying delivery records

Use `GET /v1/notifications` to query the log. All parameters are optional:

```
GET /v1/notifications?status=failed&agent_id=report-agent&limit=50
```

| Query parameter | Description |
|-----------------|-------------|
| `status` | Filter by `delivered` or `failed` |
| `agent_id` | Filter by agent |
| `channel` | Filter by `slack` or `webhook` |
| `execution_id` | Filter to a specific execution |
| `limit` | Page size (default: 50) |
| `offset` | Pagination offset (default: 0) |

Response shape:

```json
{
  "items": [
    {
      "id": "01J...",
      "execution_id": "abc-123",
      "agent_id": "report-agent",
      "event_type": "on_error",
      "channel": "slack",
      "target": "#alerts",
      "status": "failed",
      "attempts": 3,
      "last_error": "channel_not_found",
      "created_at": "2026-02-25T09:00:00Z",
      "delivered_at": null
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### Dashboard

The built-in dashboard exposes a **Notifications** page at `/dashboard/notifications`. It lists all delivery records and provides a **Retry** button for failed deliveries, which re-dispatches the notification immediately outside of any scheduled cadence.

!!! note
    Delivery tracking is only available when a persistence backend (SQLite or PostgreSQL) is configured. Without persistence the `GET /v1/notifications` endpoint returns an empty result set and the dashboard notifications page will be empty.
