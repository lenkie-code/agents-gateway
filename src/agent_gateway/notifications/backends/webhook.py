"""Outbound webhook notification backend with HMAC signing and custom payloads."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from agent_gateway.notifications.models import NotificationEvent, NotificationTarget

logger = logging.getLogger(__name__)

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fd00::/8"),
]

_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal"}


def _validate_webhook_url(url: str) -> None:
    """Reject URLs targeting private/internal networks (SSRF protection)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Missing hostname in webhook URL")
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Blocked hostname: {hostname}")
    try:
        addr = ipaddress.ip_address(hostname)
        if any(addr in net for net in _BLOCKED_NETWORKS):
            raise ValueError(f"Webhook URL resolves to blocked network: {hostname}")
    except ValueError as exc:
        if "blocked" in str(exc).lower() or "Unsupported" in str(exc):
            raise
        # hostname is a DNS name, not an IP literal — allowed


@dataclass
class WebhookEndpoint:
    """A registered webhook destination."""

    name: str
    url: str
    secret: str = ""
    events: list[str] = field(default_factory=list)  # empty = all events
    payload_template: str | None = None  # Jinja2 template string


class WebhookBackend:
    """Outbound webhook notification backend with HMAC signing.

    Supports two modes:
    - Global endpoints registered via fluent API or gateway.yaml (referenced by name)
    - Inline URLs defined per-agent in CONFIG.md (no global registration needed)
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

        for ep in endpoints or []:
            self._endpoints[ep.name] = ep

    def add_endpoint(self, endpoint: WebhookEndpoint) -> None:
        """Register a global webhook endpoint."""
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
        if self._client is None:
            raise RuntimeError("WebhookBackend not initialized — call initialize() first")

        # Resolve URL, secret, and template from either inline or global mode
        url: str
        secret: str
        payload_template: str | None

        if target.url:
            # Inline mode: agent defines its own URL, secret, and template
            url = target.url
            secret = target.secret or self._default_secret
            payload_template = target.payload_template
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
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if secret:
            timestamp = str(int(time.time()))
            signature = self._sign(body, secret, timestamp)
            headers["X-AgentGateway-Signature"] = f"sha256={signature}"
            headers["X-AgentGateway-Timestamp"] = timestamp

        _validate_webhook_url(url)
        response = await self._client.post(url, content=body, headers=headers)
        response.raise_for_status()

    @staticmethod
    def _build_payload(
        event: NotificationEvent,
        payload_template: str | None,
    ) -> dict[str, Any]:
        """Build webhook payload. Custom template or default schema."""
        if payload_template:
            from agent_gateway.notifications.template import render_template_string

            rendered = render_template_string(payload_template, event=event)
            result: dict[str, Any] = json.loads(rendered)
            return result

        # Default payload — just the event data, no internal metrics
        result = event.result or {}
        payload: dict[str, Any] = {
            "event": event.type,
            "execution_id": event.execution_id,
            "agent_id": event.agent_id,
            "status": event.status,
            "message": event.message[:4096],
            "output": result.get("output"),
            "duration_ms": event.duration_ms,
        }
        if event.error:
            payload["error"] = event.error
        return payload

    @staticmethod
    def _sign(body: str, secret: str, timestamp: str) -> str:
        """Compute HMAC-SHA256 signature."""
        signing_input = f"{timestamp}.{body}"
        return hmac.new(
            secret.encode(),
            signing_input.encode(),
            hashlib.sha256,
        ).hexdigest()
