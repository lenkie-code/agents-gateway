---
title: "feat: Pluggable Notification Backends (Slack + Webhooks)"
type: feat
status: completed
date: 2026-02-19
depends_on: [08-api-layer-and-gateway, 2026-02-18-feat-pluggable-persistence-backends-plan]
parent: 2026-02-18-feat-agent-gateway-framework-plan.md
---

# Pluggable Notification Backends (Slack + Webhooks)

## Overview

Implement a pluggable notification system following the same Protocol-based architecture as persistence, queue, and auth. Ship Slack and Webhooks as optional pip extras (`agent-gateway[slack]`, `agent-gateway[webhooks]`). Notifications fire after long-running agent executions complete (or fail), with per-agent configuration via CONFIG.md frontmatter. Slack messages use professional Block Kit formatting with customizable templates. Webhooks support custom payload schemas via Jinja2 templates.

## Problem Statement

The `notifications/` package is empty — `NotificationsConfig` exists in `config.py` but nothing reads it. Long-running async agents complete silently; users have no way to know when an execution finishes without polling. The framework needs fire-and-forget outbound notifications that:

1. **Are pluggable** — same Protocol pattern as `PersistenceBackend`, `ExecutionQueue`, `AuthProvider`
2. **Are optional** — `agent-gateway[slack]` and `agent-gateway[webhooks]` pip extras
3. **Are per-agent** — each agent declares its own notification rules in CONFIG.md
4. **Never affect execution** — notification failure is logged, never crashes or changes execution status
5. **Support customization** — Slack Block Kit templates and webhook payload schemas

## Proposed Solution

A three-layer architecture mirroring persistence:

```
┌─────────────────────────────────────────────────────┐
│  Gateway / Engine / WorkerPool  (consumers)         │
│  Import only: models.py + protocols.py              │
├─────────────────────────────────────────────────────┤
│  notifications/models.py     — plain @dataclass     │
│  notifications/protocols.py  — typing.Protocol      │
│  notifications/engine.py     — NotificationEngine   │
├─────────────────────────────────────────────────────┤
│  notifications/backends/slack.py      — Block Kit   │
│  notifications/backends/webhook.py    — HMAC+schema │
│  notifications/backends/???/          — future      │
└─────────────────────────────────────────────────────┘
```

## Dream API

### Fluent API (Python)

```python
from agent_gateway import Gateway

gw = Gateway(workspace="./workspace")

# Slack
gw.use_slack_notifications(
    bot_token="xoxb-...",
    default_channel="#agent-alerts",
)

# Webhooks
gw.use_webhook_notifications(
    url="https://api.example.com/hooks/agent-events",
    secret="whsec_...",
    events=["execution.completed", "execution.failed"],
)

# Custom backend
gw.use_notifications(MyCustomNotifier())

# Disable (explicit)
gw.use_notifications(None)

gw.run()
```

### Agent CONFIG.md (Per-Agent)

Each agent controls its own notification routing. Different agents can post to different Slack channels, different webhook URLs, and use different templates.

**Underwriting agent** — posts to a domain-specific Slack channel + CRM webhook:

```yaml
# workspace/agents/underwriting/CONFIG.md
---
model:
  name: anthropic/claude-sonnet-4-5-20250929

execution_mode: async

notifications:
  on_complete:
    - channel: slack
      target: "#underwriting-alerts"
      template: underwriting-complete    # custom Block Kit template
    - channel: webhook
      target: crm-integration           # references a global endpoint by name
  on_error:
    - channel: slack
      target: "#engineering-alerts"
    - channel: webhook
      url: "https://pagerduty.example.com/hook"  # inline URL — no global registration needed
      secret: "${PAGERDUTY_WEBHOOK_SECRET}"
---
```

**Sales agent** — different channel, different webhook, different template:

```yaml
# workspace/agents/sales/CONFIG.md
---
model:
  name: google/gemini-2.5-flash

execution_mode: async

notifications:
  on_complete:
    - channel: slack
      target: "#sales-notifications"
    - channel: webhook
      url: "https://api.hubspot.com/webhooks/agent-results"
      secret: "${HUBSPOT_WEBHOOK_SECRET}"
      payload_template: |
        {
          "deal_id": "{{ event.context.deal_id }}",
          "qualification": {{ event.result | tojson }}
        }
  on_error:
    - channel: slack
      target: "#sales-notifications"
---
```

**Compliance agent** — webhook only, no Slack:

```yaml
# workspace/agents/compliance/CONFIG.md
---
model:
  name: anthropic/claude-opus-4-6

notifications:
  on_complete:
    - channel: webhook
      url: "https://compliance.internal/api/audit-events"
      secret: "${COMPLIANCE_WEBHOOK_SECRET}"
      payload_template: |
        {
          "type": "compliance_review",
          "execution_id": "{{ event.execution_id }}",
          "result": {{ event.result | tojson }},
          "timestamp": "{{ event.completed_at.isoformat() }}"
        }
---
```

**Key flexibility points:**
- Webhook `target` references a globally registered endpoint by name (from `gateway.yaml` or fluent API)
- Webhook `url` is an inline URL — the agent defines its own endpoint, no global registration needed
- Each agent can define its own `payload_template` and `secret` inline
- Slack `target` is always the channel name — each agent picks its own channel
- Slack `template` references a workspace template file — each agent can have its own visual layout

### YAML Config (gateway.yaml)

```yaml
notifications:
  slack:
    enabled: true
    bot_token: "${SLACK_BOT_TOKEN}"
    default_channel: "#agent-alerts"
  webhooks:
    - name: crm-integration
      url: "https://api.example.com/hooks/agent-events"
      secret: "${WEBHOOK_SECRET_CRM}"
      events: ["execution.completed", "execution.failed"]
      payload_template: |
        {
          "event": "{{ event.type }}",
          "agent": "{{ event.agent_id }}",
          "execution_id": "{{ event.execution_id }}",
          "status": "{{ event.status }}",
          "result": {{ event.result | tojson }},
          "completed_at": "{{ event.completed_at }}"
        }
  webhook_secret: "${WEBHOOK_SECRET}"     # default secret for all webhooks
```

### Slack Message Templates (Workspace Files)

Custom Slack templates live in the workspace as JSON Block Kit files:

```
workspace/
└── templates/
    └── notifications/
        ├── default-complete.json       # built-in, shipped with package
        ├── default-error.json          # built-in, shipped with package
        └── underwriting-complete.json  # user-defined custom template
```

Templates are Jinja2-rendered Block Kit JSON with access to execution context variables.

## Technical Approach

### Architecture

#### Layer 1: Notification Models

**File:** `src/agent_gateway/notifications/models.py`

Plain dataclasses with zero optional-dependency imports. These flow through the engine and into backends.

```python
# notifications/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

@dataclass(frozen=True)
class NotificationEvent:
    """Immutable event fired when an execution reaches a terminal state."""
    type: str                      # execution.completed | execution.failed | execution.timeout
    execution_id: str
    agent_id: str
    status: str
    message: str                   # the original user message
    result: dict[str, Any] | None = None
    error: str | None = None
    usage: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int = 0
    context: dict[str, Any] | None = None

@dataclass(frozen=True)
class NotificationTarget:
    """A single notification destination parsed from agent CONFIG.md.

    For Slack:
      - target: "#channel-name"
      - template: optional custom Block Kit template name

    For Webhook (two modes):
      - target: "crm-integration"  → references a globally registered endpoint by name
      - url: "https://..."         → inline endpoint, no global registration needed
        secret: optional HMAC secret
        payload_template: optional inline Jinja2 template
    """
    channel: str                         # "slack" | "webhook"
    target: str = ""                     # Slack channel or global webhook name
    template: str | None = None          # Slack Block Kit template name
    url: str | None = None               # Inline webhook URL (per-agent)
    secret: str | None = None            # Inline webhook HMAC secret (per-agent)
    payload_template: str | None = None  # Inline webhook Jinja2 payload (per-agent)

@dataclass(frozen=True)
class AgentNotificationConfig:
    """Per-agent notification rules, parsed from CONFIG.md frontmatter."""
    on_complete: list[NotificationTarget] = field(default_factory=list)
    on_error: list[NotificationTarget] = field(default_factory=list)
    on_timeout: list[NotificationTarget] = field(default_factory=list)
```

#### Layer 2: Protocol

**File:** `src/agent_gateway/notifications/protocols.py`

```python
# notifications/protocols.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
from agent_gateway.notifications.models import NotificationEvent, NotificationTarget

@runtime_checkable
class NotificationBackend(Protocol):
    """Contract for a pluggable notification backend."""

    @property
    def channel(self) -> str:
        """The channel identifier this backend handles (e.g. 'slack', 'webhook')."""
        ...

    async def initialize(self) -> None:
        """Validate config, establish connections. Idempotent."""
        ...

    async def dispose(self) -> None:
        """Close connections and release resources."""
        ...

    async def send(
        self,
        event: NotificationEvent,
        target: NotificationTarget,
    ) -> None:
        """Send a notification. Raise on failure (engine handles retries)."""
        ...
```

#### Layer 3: Notification Engine

**File:** `src/agent_gateway/notifications/engine.py`

The engine is the dispatcher. It maps event types to agent notification rules, resolves the correct backend for each channel, and handles retries + error isolation.

```python
# notifications/engine.py
import asyncio
import logging
from agent_gateway.notifications.models import (
    AgentNotificationConfig,
    NotificationEvent,
    NotificationTarget,
)
from agent_gateway.notifications.protocols import NotificationBackend

logger = logging.getLogger(__name__)

# Maps event type → config attribute name
_EVENT_ROUTING: dict[str, str] = {
    "execution.completed": "on_complete",
    "execution.failed": "on_error",
    "execution.timeout": "on_timeout",
}

MAX_RETRIES = 3
BACKOFF_BASE_S = 1.0  # 1s, 2s, 4s


class NotificationEngine:
    """Dispatches notifications to registered backends. Fire-and-forget."""

    def __init__(self) -> None:
        self._backends: dict[str, NotificationBackend] = {}

    def register(self, backend: NotificationBackend) -> None:
        self._backends[backend.channel] = backend

    @property
    def has_backends(self) -> bool:
        return len(self._backends) > 0

    async def initialize(self) -> None:
        for backend in self._backends.values():
            await backend.initialize()

    async def dispose(self) -> None:
        for backend in self._backends.values():
            try:
                await backend.dispose()
            except Exception:
                logger.warning("Failed to dispose %s backend", backend.channel, exc_info=True)

    async def notify(
        self,
        event: NotificationEvent,
        config: AgentNotificationConfig,
    ) -> None:
        """Fire-and-forget: dispatch notifications as background tasks.

        Never raises — all errors are logged and swallowed.
        """
        attr_name = _EVENT_ROUTING.get(event.type)
        if attr_name is None:
            return

        targets: list[NotificationTarget] = getattr(config, attr_name, [])
        if not targets:
            return

        tasks = [
            asyncio.create_task(self._send_with_retry(event, t))
            for t in targets
        ]
        # Fire-and-forget: gather but swallow all exceptions
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_with_retry(
        self,
        event: NotificationEvent,
        target: NotificationTarget,
    ) -> None:
        backend = self._backends.get(target.channel)
        if backend is None:
            logger.warning(
                "No backend registered for channel %r (target: %s)",
                target.channel,
                target.target,
            )
            return

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                await backend.send(event, target)
                return
            except Exception as exc:
                last_exc = exc
                wait = BACKOFF_BASE_S * (2 ** attempt)
                logger.warning(
                    "Notification to %s/%s failed (attempt %d/%d), retrying in %.1fs: %s",
                    target.channel, target.target, attempt + 1, MAX_RETRIES, wait, exc,
                )
                await asyncio.sleep(wait)

        logger.error(
            "Notification to %s/%s failed after %d attempts: %s",
            target.channel, target.target, MAX_RETRIES, last_exc,
        )
```

#### Slack Backend

**File:** `src/agent_gateway/notifications/backends/slack.py`

Uses `slack-bolt` (optional dependency via `agent-gateway[slack]`). Sends professional Block Kit messages with customizable templates.

```python
# notifications/backends/slack.py
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_gateway.notifications.models import NotificationEvent, NotificationTarget
from agent_gateway.notifications.template import render_template

logger = logging.getLogger(__name__)


class SlackBackend:
    """Slack notification backend using Block Kit rich formatting.

    Requires: pip install agent-gateway[slack]
    """

    def __init__(
        self,
        bot_token: str,
        default_channel: str = "#agent-alerts",
        templates_dir: Path | None = None,
    ) -> None:
        try:
            from slack_sdk.web.async_client import AsyncWebClient
        except ImportError:
            raise ImportError(
                "Slack backend requires the slack extra: "
                "pip install agent-gateway[slack]"
            ) from None

        self._bot_token = bot_token
        self._default_channel = default_channel
        self._templates_dir = templates_dir
        self._client: AsyncWebClient | None = None

    @property
    def channel(self) -> str:
        return "slack"

    async def initialize(self) -> None:
        from slack_sdk.web.async_client import AsyncWebClient
        self._client = AsyncWebClient(token=self._bot_token)

    async def dispose(self) -> None:
        self._client = None

    async def send(
        self,
        event: NotificationEvent,
        target: NotificationTarget,
    ) -> None:
        assert self._client is not None
        channel = target.target or self._default_channel
        blocks = self._build_blocks(event, target)
        fallback_text = self._build_fallback_text(event)

        await self._client.chat_postMessage(
            channel=channel,
            blocks=blocks,
            text=fallback_text,  # fallback for notifications/plain-text clients
        )

    def _build_blocks(
        self,
        event: NotificationEvent,
        target: NotificationTarget,
    ) -> list[dict[str, Any]]:
        """Build Slack Block Kit blocks.

        If a custom template is specified, render it.
        Otherwise use the professional default layout.
        """
        # Try custom template first
        if target.template and self._templates_dir:
            template_path = self._templates_dir / f"{target.template}.json.j2"
            if template_path.exists():
                rendered = render_template(template_path, event=event, target=target)
                return json.loads(rendered)

        # Try event-type default template
        if self._templates_dir:
            event_template = self._templates_dir / f"default-{event.type.split('.')[-1]}.json.j2"
            if event_template.exists():
                rendered = render_template(event_template, event=event, target=target)
                return json.loads(rendered)

        # Built-in professional default
        return self._default_blocks(event)

    def _default_blocks(self, event: NotificationEvent) -> list[dict[str, Any]]:
        """Professional default Block Kit layout."""
        status_emoji = {
            "execution.completed": ":white_check_mark:",
            "execution.failed": ":x:",
            "execution.timeout": ":warning:",
        }.get(event.type, ":bell:")

        status_text = {
            "execution.completed": "Completed",
            "execution.failed": "Failed",
            "execution.timeout": "Timed Out",
        }.get(event.type, event.status)

        # Header
        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{status_emoji}  Agent Execution {status_text}",
                    "emoji": True,
                },
            },
            {"type": "divider"},
        ]

        # Agent + Execution ID fields
        fields = [
            {
                "type": "mrkdwn",
                "text": f"*Agent*\n`{event.agent_id}`",
            },
            {
                "type": "mrkdwn",
                "text": f"*Execution ID*\n`{event.execution_id}`",
            },
        ]

        # Duration
        if event.duration_ms:
            duration_s = event.duration_ms / 1000
            if duration_s >= 60:
                duration_str = f"{duration_s / 60:.1f}m"
            else:
                duration_str = f"{duration_s:.1f}s"
            fields.append({
                "type": "mrkdwn",
                "text": f"*Duration*\n{duration_str}",
            })

        # Cost
        if event.usage and event.usage.get("cost_usd"):
            fields.append({
                "type": "mrkdwn",
                "text": f"*Cost*\n${event.usage['cost_usd']:.4f}",
            })

        blocks.append({"type": "section", "fields": fields})

        # User message (truncated)
        if event.message:
            truncated = event.message[:300]
            if len(event.message) > 300:
                truncated += "..."
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Input*\n>{truncated}",
                },
            })

        # Result or Error
        if event.type == "execution.completed" and event.result:
            result_text = _format_result(event.result)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Result*\n```{result_text}```",
                },
            })
        elif event.error:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error*\n```{event.error[:1000]}```",
                },
            })

        # Footer with timestamp
        completed = event.completed_at or datetime.now(timezone.utc)
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"agent-gateway | "
                        f"{completed.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    ),
                },
            ],
        })

        return blocks

    @staticmethod
    def _build_fallback_text(event: NotificationEvent) -> str:
        return (
            f"Agent '{event.agent_id}' execution {event.status}: "
            f"{event.execution_id}"
        )


def _format_result(result: dict, max_len: int = 2000) -> str:
    """Format result dict as readable text, truncated to max_len."""
    text = json.dumps(result, indent=2, default=str)
    if len(text) > max_len:
        text = text[:max_len] + "\n... (truncated)"
    return text
```

#### Webhook Backend

**File:** `src/agent_gateway/notifications/backends/webhook.py`

Generic outbound webhooks with HMAC-SHA256 signing and customizable payload schemas via Jinja2 templates.

```python
# notifications/backends/webhook.py
from __future__ import annotations
import hashlib
import hmac
import json
import logging
import time
from typing import Any

import httpx

from agent_gateway.notifications.models import NotificationEvent, NotificationTarget
from agent_gateway.notifications.template import render_template_string

logger = logging.getLogger(__name__)


@dataclass
class WebhookEndpoint:
    """A registered webhook destination."""
    name: str
    url: str
    secret: str = ""
    events: list[str] = field(default_factory=list)  # empty = all events
    payload_template: str | None = None                # Jinja2 template string


class WebhookBackend:
    """Outbound webhook notification backend with HMAC signing.

    Requires: pip install agent-gateway[webhooks]
    """

    def __init__(
        self,
        endpoints: list[WebhookEndpoint] | None = None,
        default_secret: str = "",
        timeout_s: float = 10.0,
    ) -> None:
        self._endpoints: dict[str, WebhookEndpoint] = {}
        self._default_secret = default_secret
        self._timeout_s = timeout_s
        self._client: httpx.AsyncClient | None = None

        for ep in (endpoints or []):
            self._endpoints[ep.name] = ep

    def add_endpoint(self, endpoint: WebhookEndpoint) -> None:
        self._endpoints[endpoint.name] = endpoint

    @property
    def channel(self) -> str:
        return "webhook"

    async def initialize(self) -> None:
        self._client = httpx.AsyncClient(timeout=self._timeout_s)

    async def dispose(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def send(
        self,
        event: NotificationEvent,
        target: NotificationTarget,
    ) -> None:
        assert self._client is not None

        # Two modes: inline URL (per-agent) or global endpoint reference (by name)
        if target.url:
            # Inline mode: agent defines its own URL, secret, and payload template
            url = target.url
            secret = target.secret or self._default_secret
            payload_template = target.payload_template
            # No event filtering for inline — agent controls this via on_complete/on_error
        elif target.target:
            # Global reference mode: look up pre-registered endpoint by name
            endpoint = self._endpoints.get(target.target)
            if endpoint is None:
                logger.warning("Unknown webhook endpoint: %s", target.target)
                return
            if endpoint.events and event.type not in endpoint.events:
                return
            url = endpoint.url
            secret = endpoint.secret or self._default_secret
            payload_template = target.payload_template or endpoint.payload_template
        else:
            logger.warning("Webhook target has no url or name")
            return

        # Build payload
        payload = self._build_payload(event, payload_template)
        body = json.dumps(payload, default=str)

        # Sign
        headers = {"Content-Type": "application/json"}
        if secret:
            timestamp = str(int(time.time()))
            signature = self._sign(body, secret, timestamp)
            headers["X-AgentGateway-Signature"] = f"sha256={signature}"
            headers["X-AgentGateway-Timestamp"] = timestamp

        response = await self._client.post(url, content=body, headers=headers)
        response.raise_for_status()

    def _build_payload(
        self,
        event: NotificationEvent,
        payload_template: str | None,
    ) -> dict[str, Any]:
        """Build webhook payload. Custom template or default schema."""
        if payload_template:
            rendered = render_template_string(
                payload_template,
                event=event,
            )
            return json.loads(rendered)

        # Default payload schema
        return {
            "event": event.type,
            "execution_id": event.execution_id,
            "agent_id": event.agent_id,
            "status": event.status,
            "message": event.message[:4096],
            "result": event.result,
            "error": event.error,
            "usage": event.usage,
            "started_at": event.started_at.isoformat() if event.started_at else None,
            "completed_at": event.completed_at.isoformat() if event.completed_at else None,
            "duration_ms": event.duration_ms,
            "context": event.context,
        }

    @staticmethod
    def _sign(body: str, secret: str, timestamp: str) -> str:
        signing_input = f"{timestamp}.{body}"
        return hmac.new(
            secret.encode(),
            signing_input.encode(),
            hashlib.sha256,
        ).hexdigest()
```

#### Template Rendering

**File:** `src/agent_gateway/notifications/template.py`

Thin Jinja2 wrapper for rendering notification templates. Jinja2 is already a transitive dependency via several packages but is added explicitly.

```python
# notifications/template.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, BaseLoader, FileSystemLoader, select_autoescape


def render_template(path: Path, **context: Any) -> str:
    """Render a Jinja2 template file with the given context."""
    env = Environment(
        loader=FileSystemLoader(path.parent),
        autoescape=select_autoescape([]),
    )
    env.filters["tojson"] = lambda v: json.dumps(v, default=str)
    template = env.get_template(path.name)
    return template.render(**context)


def render_template_string(source: str, **context: Any) -> str:
    """Render an inline Jinja2 template string."""
    env = Environment(
        loader=BaseLoader(),
        autoescape=select_autoescape([]),
    )
    env.filters["tojson"] = lambda v: json.dumps(v, default=str)
    template = env.from_string(source)
    return template.render(**context)
```

### Agent Definition Changes

**File:** `src/agent_gateway/workspace/agent.py`

Add `notifications` to `AgentDefinition` and parse it from CONFIG.md frontmatter.

```python
# Added to AgentDefinition
@dataclass
class AgentDefinition:
    id: str
    path: Path
    agent_prompt: str
    soul_prompt: str = ""
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    model: AgentModelConfig = field(default_factory=AgentModelConfig)
    schedules: list[ScheduleConfig] = field(default_factory=list)
    execution_mode: str = "sync"
    notifications: AgentNotificationConfig = field(default_factory=AgentNotificationConfig)  # NEW
```

**Parsing** — in the `load()` classmethod, after extracting `execution_mode`:

```python
# Parse notifications from CONFIG.md (or AGENT.md) frontmatter
raw_notif = merged.get("notifications", {})
notifications = AgentNotificationConfig(
    on_complete=[
        NotificationTarget(**t) for t in raw_notif.get("on_complete", [])
    ],
    on_error=[
        NotificationTarget(**t) for t in raw_notif.get("on_error", [])
    ],
    on_timeout=[
        NotificationTarget(**t) for t in raw_notif.get("on_timeout", [])
    ],
)
```

### Gateway Fluent API

**Changes to:** `src/agent_gateway/gateway.py`

```python
class Gateway(FastAPI):
    def __init__(self, ...):
        # ... existing fields
        self._notification_engine: NotificationEngine = NotificationEngine()
        self._notification_backends: list[NotificationBackend] = []  # pre-startup buffer

    # --- Slack ---

    def use_slack_notifications(
        self,
        bot_token: str,
        default_channel: str = "#agent-alerts",
        templates_dir: Path | str | None = None,
    ) -> Gateway:
        """Configure Slack notifications. Requires: pip install agent-gateway[slack]"""
        if self._started:
            raise RuntimeError("Cannot configure notifications after gateway has started")
        from agent_gateway.notifications.backends.slack import SlackBackend
        templates = Path(templates_dir) if templates_dir else None
        backend = SlackBackend(
            bot_token=bot_token,
            default_channel=default_channel,
            templates_dir=templates,
        )
        self._notification_backends.append(backend)
        return self

    # --- Webhooks ---

    def use_webhook_notifications(
        self,
        url: str,
        name: str = "default",
        secret: str = "",
        events: list[str] | None = None,
        payload_template: str | None = None,
    ) -> Gateway:
        """Add a webhook notification endpoint. Requires: pip install agent-gateway[webhooks]"""
        if self._started:
            raise RuntimeError("Cannot configure notifications after gateway has started")
        from agent_gateway.notifications.backends.webhook import (
            WebhookBackend, WebhookEndpoint,
        )
        # Find or create WebhookBackend
        existing = next(
            (b for b in self._notification_backends if isinstance(b, WebhookBackend)),
            None,
        )
        endpoint = WebhookEndpoint(
            name=name,
            url=url,
            secret=secret,
            events=events or [],
            payload_template=payload_template,
        )
        if existing is not None:
            existing.add_endpoint(endpoint)
        else:
            backend = WebhookBackend(endpoints=[endpoint])
            self._notification_backends.append(backend)
        return self

    # --- Custom / disable ---

    def use_notifications(self, backend: NotificationBackend | None) -> Gateway:
        """Register a custom notification backend, or None to disable all."""
        if self._started:
            raise RuntimeError("Cannot configure notifications after gateway has started")
        if backend is None:
            self._notification_backends.clear()
        else:
            self._notification_backends.append(backend)
        return self
```

### Startup Integration

In `_startup()`, after persistence and queue initialization (step 6.5):

```python
# 6.5: Notifications
for backend in self._notification_backends:
    self._notification_engine.register(backend)

# If no fluent API backends, check gateway.yaml config
if not self._notification_engine.has_backends:
    self._init_notifications_from_config(self._config.notifications)

try:
    await self._notification_engine.initialize()
except Exception:
    logger.warning("Failed to initialize notification backends", exc_info=True)
```

### Execution Integration Points

**Point 1: Synchronous execution** — in `gateway.py` `_execute_inline()` or wherever sync invoke completes:

```python
# After execution completes, fire notification in background
if self._notification_engine.has_backends:
    agent_def = self._snapshot.workspace.agents.get(agent_id)
    if agent_def:
        event = _build_notification_event(execution_record)
        asyncio.create_task(
            self._notification_engine.notify(event, agent_def.notifications)
        )
```

**Point 2: Worker pool** — in `queue/worker.py` `_run_execution()`, after updating persistence with final status:

```python
# After saving execution result
if self._notification_engine.has_backends:
    agent_def = snapshot.workspace.agents.get(job.agent_id)
    if agent_def:
        event = _build_notification_event(execution_id, status, result, ...)
        await self._notification_engine.notify(event, agent_def.notifications)
```

The helper function:

```python
def _build_notification_event(record: ExecutionRecord) -> NotificationEvent:
    event_type = {
        "completed": "execution.completed",
        "failed": "execution.failed",
        "timeout": "execution.timeout",
    }.get(record.status, f"execution.{record.status}")

    return NotificationEvent(
        type=event_type,
        execution_id=record.id,
        agent_id=record.agent_id,
        status=record.status,
        message=record.message,
        result=record.result,
        error=record.error,
        usage=record.usage,
        started_at=record.started_at,
        completed_at=record.completed_at,
        duration_ms=int(
            (record.completed_at - record.started_at).total_seconds() * 1000
        ) if record.completed_at and record.started_at else 0,
        context=record.context,
    )
```

### Updated pyproject.toml Extras

```toml
[project.optional-dependencies]
slack = ["slack-bolt>=1.18", "slack-sdk>=3.27"]
webhooks = ["jinja2>=3.1"]
# ... existing extras unchanged
all = ["agent-gateway[sqlite,postgres,otlp,slack,webhooks,redis,rabbitmq,oauth2]"]
```

Note: `httpx` is already a core dependency. `jinja2` is explicitly added for the webhooks extra since template rendering depends on it.

### File Structure

```
src/agent_gateway/notifications/
    __init__.py              # UPDATED: public exports
    models.py                # NEW: NotificationEvent, NotificationTarget, AgentNotificationConfig
    protocols.py             # NEW: NotificationBackend protocol
    engine.py                # NEW: NotificationEngine (dispatch + retry)
    template.py              # NEW: Jinja2 template rendering helpers
    backends/
        __init__.py
        slack.py             # NEW: SlackBackend (Block Kit)
        webhook.py           # NEW: WebhookBackend (HMAC + custom payloads)
```

### Slack Template Example

**File:** `workspace/templates/notifications/underwriting-complete.json.j2`

```json
[
  {
    "type": "header",
    "text": {
      "type": "plain_text",
      "text": ":briefcase:  Underwriting Assessment Complete",
      "emoji": true
    }
  },
  {"type": "divider"},
  {
    "type": "section",
    "fields": [
      {"type": "mrkdwn", "text": "*Agent*\n`{{ event.agent_id }}`"},
      {"type": "mrkdwn", "text": "*Decision*\n`{{ event.result.output.recommendation | default('N/A') }}`"},
      {"type": "mrkdwn", "text": "*Risk Score*\n`{{ event.result.output.score | default('—') }}`"},
      {"type": "mrkdwn", "text": "*Duration*\n{{ (event.duration_ms / 1000) | round(1) }}s"}
    ]
  },
  {% if event.result and event.result.output and event.result.output.reasoning %}
  {
    "type": "section",
    "text": {
      "type": "mrkdwn",
      "text": "*Reasoning*\n{% for r in event.result.output.reasoning %}• {{ r }}\n{% endfor %}"
    }
  },
  {% endif %}
  {
    "type": "context",
    "elements": [
      {
        "type": "mrkdwn",
        "text": "Execution `{{ event.execution_id }}` | {{ event.completed_at.strftime('%Y-%m-%d %H:%M UTC') }}"
      }
    ]
  }
]
```

### Custom Webhook Payload Schema Example

In `gateway.yaml`:

```yaml
notifications:
  webhooks:
    - name: crm-integration
      url: "https://api.example.com/hooks/agent-events"
      secret: "${WEBHOOK_SECRET_CRM}"
      events: ["execution.completed"]
      payload_template: |
        {
          "type": "agent_result",
          "data": {
            "deal_id": "{{ event.context.deal_id | default('unknown') }}",
            "agent": "{{ event.agent_id }}",
            "decision": {{ event.result.output | tojson }},
            "cost_usd": {{ event.usage.cost_usd | default(0) }},
            "timestamp": "{{ event.completed_at.isoformat() }}"
          }
        }
```

### Updated NotificationsConfig

**File:** `src/agent_gateway/config.py`

```python
class SlackConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    default_channel: str = "#agent-alerts"       # NEW

class WebhookEndpointConfig(BaseModel):          # RENAMED from WebhookConfig
    name: str
    url: str
    secret: str = ""
    events: list[str] = Field(default_factory=list)
    payload_template: str | None = None           # NEW: Jinja2 template string

class NotificationsConfig(BaseModel):
    slack: SlackConfig = SlackConfig()
    webhooks: list[WebhookEndpointConfig] = Field(default_factory=list)
    webhook_secret: str = ""
```

Removed `TeamsConfig` from the config — Teams is out of scope for this phase.

## Implementation Phases

### Phase 1: Core Models & Protocol

**Goal:** Establish the notification domain types and protocol contract.

- [x] Create `notifications/models.py` with `NotificationEvent`, `NotificationTarget`, `AgentNotificationConfig`
- [x] Create `notifications/protocols.py` with `NotificationBackend` protocol
- [x] Create `notifications/engine.py` with dispatch + retry logic
- [x] Update `notifications/__init__.py` with public exports
- [x] Unit tests for `NotificationEngine` with mock backends

**Estimated files changed:** 4 new, 1 updated
**Risk:** Low — additive, no existing code changes

### Phase 2: Agent Definition & Config

**Goal:** Parse notification config from agent CONFIG.md frontmatter and update gateway config.

- [x] Add `notifications: AgentNotificationConfig` field to `AgentDefinition`
- [x] Parse `notifications` from CONFIG.md frontmatter in `AgentDefinition.load()`
- [x] Update `NotificationsConfig` in `config.py` (add `default_channel`, `payload_template`, remove `TeamsConfig`)
- [x] Update test workspace fixtures with notification config
- [x] Unit tests for frontmatter parsing with notifications

**Estimated files changed:** 3 (agent.py, config.py, tests)
**Risk:** Low — extends existing parsing, backward compatible (no notifications = empty config)

### Phase 3: Slack Backend

**Goal:** Professional Slack notifications with Block Kit and custom templates.

- [x] Create `notifications/backends/slack.py` with `SlackBackend`
- [x] Create `notifications/template.py` with Jinja2 rendering helpers
- [x] Implement default Block Kit layouts for completed/failed/timeout events
- [x] Support custom templates from `workspace/templates/notifications/`
- [x] Unit tests with mocked Slack client
- [x] Verify `agent-gateway[slack]` extra installs correctly

**Estimated files changed:** 3 new
**Risk:** Medium — Block Kit JSON structure needs testing for Slack API compatibility

### Phase 4: Webhook Backend

**Goal:** Outbound webhooks with HMAC signing and custom payload schemas.

- [x] Create `notifications/backends/webhook.py` with `WebhookBackend`
- [x] Implement HMAC-SHA256 signing (`X-AgentGateway-Signature`, `X-AgentGateway-Timestamp`)
- [x] Support custom payload templates via Jinja2 (`payload_template` field)
- [x] Support event filtering (`events` list)
- [x] Add `jinja2>=3.1` to `[webhooks]` extra in pyproject.toml
- [x] Unit tests with httpx mock
- [x] Verify HMAC signature generation/verification round-trip

**Estimated files changed:** 2 new, 1 updated (pyproject.toml)
**Risk:** Low — straightforward HTTP POST + HMAC

### Phase 5: Gateway Integration

**Goal:** Wire notification engine into Gateway lifecycle and execution flow.

- [x] Add fluent API methods: `use_slack_notifications()`, `use_webhook_notifications()`, `use_notifications()`
- [x] Initialize notification engine during `_startup()` (fluent API > config)
- [x] Dispose notification engine during `_shutdown()`
- [x] Fire notifications after sync execution in `_execute_inline()` / `invoke()`
- [x] Fire notifications after async execution in `WorkerPool._run_execution()`
- [x] Add `_build_notification_event()` helper
- [x] Integration tests: full invoke → notification flow
- [x] Integration tests: async queue → notification flow

**Estimated files changed:** 3 (gateway.py, worker.py, tests)
**Risk:** Medium — touches Gateway startup/shutdown and worker pool

### Phase 6: pyproject.toml & Cleanup

**Goal:** Finalize extras and ensure clean install paths.

- [x] Verify `agent-gateway[slack]` extra works end-to-end
- [x] Verify `agent-gateway[webhooks]` extra works end-to-end
- [x] Update `all` extra to include `slack` and `webhooks`
- [x] Verify base install (no extras) gracefully handles missing notification deps
- [x] Remove `TeamsConfig` from config if still present

**Estimated files changed:** 1-2
**Risk:** Low

## Design Decisions & Edge Cases

### D1: Notification Failure Never Affects Execution

Notifications are fire-and-forget. If Slack is down or a webhook returns 500, the execution result is unaffected. Failures are logged at WARNING level. After 3 retry attempts (1s, 2s, 4s backoff), the notification is abandoned and logged at ERROR level.

### D2: Precedence — Fluent API vs gateway.yaml

Same rule as persistence: fluent API always wins. If `use_slack_notifications()` is called, the `notifications.slack` section in `gateway.yaml` is ignored. If no fluent call is made, fall back to YAML config.

### D3: Per-Agent Config is Required for Notifications to Fire

Even if Slack is configured globally, no notifications fire unless the agent's CONFIG.md has a `notifications:` block. This is deliberate — notifications are opt-in per agent. Global config provides the connection; agent config provides the routing.

### D4: Webhook Custom Payloads via Jinja2 Templates

Webhook endpoints can define a `payload_template` as an inline Jinja2 string. The template receives the full `NotificationEvent` as `event`. If no template is provided, a sensible default JSON schema is used. The `tojson` filter is available for serializing nested objects.

### D5: Slack Custom Templates via Workspace Files

Custom Slack Block Kit templates live in `workspace/templates/notifications/` as `.json.j2` files. They are referenced by name in CONFIG.md (`template: underwriting-complete`). The engine looks up `{name}.json.j2` in the templates directory. If not found, falls back to the built-in default.

### D6: No `agent-gateway[teams]` in This Phase

Microsoft Teams is explicitly out of scope. The Protocol is extensible — Teams can be added later as `notifications/backends/teams.py` without touching any existing code.

### D7: Truncation of Large Payloads

Notification payloads are truncated to prevent oversized messages:
- Slack: result text truncated to 2KB in blocks, user message to 300 chars
- Webhook: user message truncated to 4KB, full result included (webhook receivers are expected to handle large payloads)

### D8: Template Discovery Order for Slack

```
1. Custom template from CONFIG.md `template` field → workspace/templates/notifications/{name}.json.j2
2. Event-type default template → workspace/templates/notifications/default-{completed|failed|timeout}.json.j2
3. Built-in hardcoded Block Kit layout (always available, no files needed)
```

### D9: Webhook HMAC Signature Format

```
X-AgentGateway-Signature: sha256={hex_digest}
X-AgentGateway-Timestamp: {unix_epoch_seconds}

Signing input: "{timestamp}.{json_body}"
Algorithm: HMAC-SHA256
```

Consumers verify by recomputing the signature and comparing with `hmac.compare_digest`.

### D10: Webhook Targets — Two Modes

Agents can reference webhooks in two ways:

1. **Global reference** — `target: crm-integration` looks up a pre-registered endpoint (from `gateway.yaml` or `use_webhook_notifications()`). Useful when multiple agents share the same endpoint.
2. **Inline URL** — `url: "https://..."` defines the endpoint directly in the agent's CONFIG.md. No global registration needed. The agent can also specify its own `secret` and `payload_template` inline.

This means an agent can send webhooks to any URL without the gateway operator needing to register every endpoint globally. `use_webhook_notifications()` can still be called multiple times to register shared endpoints.

### D11: CONFIG.md Notification Merge Rules

`notifications` in CONFIG.md **replaces** (does not merge with) AGENT.md frontmatter notifications. This is consistent with how `execution_mode` and `model` work — CONFIG.md wins for scalar/structured config.

## Acceptance Criteria

### Functional Requirements

- [ ] `gw.use_slack_notifications(token, channel)` configures Slack backend
- [ ] `gw.use_webhook_notifications(url, name, secret)` configures webhook backend
- [ ] `gw.use_notifications(None)` disables all notifications
- [ ] `gw.use_notifications(CustomBackend())` works for any Protocol-compliant backend
- [ ] Agent CONFIG.md `notifications.on_complete` fires on successful execution
- [ ] Agent CONFIG.md `notifications.on_error` fires on failed execution
- [ ] Agent CONFIG.md `notifications.on_timeout` fires on timeout
- [ ] Slack messages use professional Block Kit formatting
- [ ] Custom Slack templates render from workspace files
- [ ] Webhooks include HMAC-SHA256 signature headers
- [ ] Webhook custom payload templates render via Jinja2
- [ ] Webhook event filtering (`events` list) works
- [ ] Retry with exponential backoff (3 attempts: 1s, 2s, 4s)
- [ ] Notification failure never affects execution status
- [ ] gateway.yaml config works as fallback when no fluent API is used
- [ ] Missing optional dependency gives clear `ImportError` with install instructions

### Non-Functional Requirements

- [ ] `notifications/models.py` has zero optional-dependency imports
- [ ] `notifications/protocols.py` has zero optional-dependency imports
- [ ] `notifications/engine.py` has zero optional-dependency imports
- [ ] `slack-bolt` / `slack-sdk` only imported inside `backends/slack.py`
- [ ] `jinja2` only imported inside `template.py` and webhook backend
- [ ] `pip install agent-gateway` (no extras) never imports slack or jinja2
- [ ] `pip install agent-gateway[slack]` pulls in `slack-bolt` and `slack-sdk`
- [ ] `pip install agent-gateway[webhooks]` pulls in `jinja2`

### Quality Gates

- [ ] All existing tests pass (no regressions)
- [ ] New unit tests for `NotificationEngine` (dispatch, retry, error isolation)
- [ ] New unit tests for `SlackBackend` (Block Kit output, template rendering)
- [ ] New unit tests for `WebhookBackend` (HMAC signing, custom payloads, event filtering)
- [ ] New unit tests for agent CONFIG.md notification parsing
- [ ] Integration test: sync invoke → Slack notification
- [ ] Integration test: async worker → webhook notification
- [ ] mypy passes with `--strict`

## References

### Internal References

- Existing (empty) notifications package: `src/agent_gateway/notifications/__init__.py`
- Notification config: `src/agent_gateway/config.py:53-67` (NotificationsConfig)
- Agent definition + frontmatter parsing: `src/agent_gateway/workspace/agent.py`
- Gateway fluent API pattern: `src/agent_gateway/gateway.py` (use_sqlite, use_postgres, use_rabbitmq)
- Worker pool execution flow: `src/agent_gateway/queue/worker.py`
- Persistence protocol pattern: `src/agent_gateway/persistence/backend.py`
- Queue protocol pattern: `src/agent_gateway/queue/protocol.py`
- Auth protocol pattern: `src/agent_gateway/auth/protocols.py`
- Original notification subplan: `docs/plans/10-notifications.md`

### External References

- [Slack Block Kit Builder](https://app.slack.com/block-kit-builder)
- [Slack Block Kit Reference](https://api.slack.com/reference/block-kit/blocks)
- [slack-sdk AsyncWebClient](https://slack.dev/python-slack-sdk/web/index.html#async)
- [Jinja2 Template Designer Documentation](https://jinja.palletsprojects.com/en/3.1.x/templates/)
- [HMAC — RFC 2104](https://datatracker.ietf.org/doc/html/rfc2104)
- [Webhook Best Practices — Stripe](https://docs.stripe.com/webhooks/best-practices)
