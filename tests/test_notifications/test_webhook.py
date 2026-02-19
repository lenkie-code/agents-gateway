"""Tests for the webhook notification backend."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from agent_gateway.notifications.backends.webhook import WebhookBackend, WebhookEndpoint
from agent_gateway.notifications.models import NotificationEvent, NotificationTarget

_DUMMY_REQUEST = httpx.Request("POST", "https://example.com")


def _make_event(**overrides: object) -> NotificationEvent:
    defaults = {
        "type": "execution.completed",
        "execution_id": "exec-456",
        "agent_id": "test-agent",
        "status": "completed",
        "message": "Summarize quarterly report",
        "duration_ms": 3200,
        "completed_at": datetime(2026, 2, 19, 12, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return NotificationEvent(**defaults)  # type: ignore[arg-type]


class TestWebhookBackendInlineMode:
    """Inline webhook mode: URL defined directly on the target."""

    async def test_send_inline_webhook(self) -> None:
        backend = WebhookBackend()
        await backend.initialize()

        event = _make_event()
        target = NotificationTarget(channel="webhook", url="https://example.com/hook")

        mock_response = httpx.Response(200, request=_DUMMY_REQUEST)
        with patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await backend.send(event, target)

            mock_post.assert_awaited_once()
            call_kwargs = mock_post.call_args
            assert call_kwargs[1]["content"] is not None
            payload = json.loads(call_kwargs[1]["content"])
            assert payload["event"] == "execution.completed"
            assert payload["execution_id"] == "exec-456"
            assert payload["agent_id"] == "test-agent"

        await backend.dispose()

    async def test_send_with_hmac_signing(self) -> None:
        backend = WebhookBackend()
        await backend.initialize()

        event = _make_event()
        target = NotificationTarget(
            channel="webhook",
            url="https://example.com/hook",
            secret="my-secret-key",
        )

        mock_response = httpx.Response(200, request=_DUMMY_REQUEST)
        with patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await backend.send(event, target)

            headers = mock_post.call_args[1]["headers"]
            assert "X-AgentGateway-Signature" in headers
            assert headers["X-AgentGateway-Signature"].startswith("sha256=")
            assert "X-AgentGateway-Timestamp" in headers

            # Verify the signature
            body = mock_post.call_args[1]["content"]
            timestamp = headers["X-AgentGateway-Timestamp"]
            signing_input = f"{timestamp}.{body}"
            expected_sig = hmac.new(
                b"my-secret-key",
                signing_input.encode(),
                hashlib.sha256,
            ).hexdigest()
            assert headers["X-AgentGateway-Signature"] == f"sha256={expected_sig}"

        await backend.dispose()

    async def test_no_signature_without_secret(self) -> None:
        backend = WebhookBackend()
        await backend.initialize()

        event = _make_event()
        target = NotificationTarget(channel="webhook", url="https://example.com/hook")

        mock_response = httpx.Response(200, request=_DUMMY_REQUEST)
        with patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await backend.send(event, target)

            headers = mock_post.call_args[1]["headers"]
            assert "X-AgentGateway-Signature" not in headers
            assert "X-AgentGateway-Timestamp" not in headers

        await backend.dispose()

    async def test_custom_payload_template(self) -> None:
        backend = WebhookBackend()
        await backend.initialize()

        event = _make_event()
        template = '{"alert": "{{ event.agent_id }} finished", "id": "{{ event.execution_id }}"}'
        target = NotificationTarget(
            channel="webhook",
            url="https://example.com/hook",
            payload_template=template,
        )

        mock_response = httpx.Response(200, request=_DUMMY_REQUEST)
        with patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await backend.send(event, target)

            payload = json.loads(mock_post.call_args[1]["content"])
            assert payload == {"alert": "test-agent finished", "id": "exec-456"}

        await backend.dispose()


class TestWebhookBackendGlobalMode:
    """Global endpoint mode: target references a pre-registered endpoint by name."""

    async def test_send_to_global_endpoint(self) -> None:
        ep = WebhookEndpoint(name="crm", url="https://crm.example.com/webhook", secret="crm-key")
        backend = WebhookBackend(endpoints=[ep])
        await backend.initialize()

        event = _make_event()
        target = NotificationTarget(channel="webhook", target="crm")

        mock_response = httpx.Response(200, request=_DUMMY_REQUEST)
        with patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await backend.send(event, target)

            assert mock_post.call_args[0][0] == "https://crm.example.com/webhook"
            headers = mock_post.call_args[1]["headers"]
            assert "X-AgentGateway-Signature" in headers

        await backend.dispose()

    async def test_unknown_global_endpoint_skipped(self) -> None:
        backend = WebhookBackend()
        await backend.initialize()

        event = _make_event()
        target = NotificationTarget(channel="webhook", target="unknown-name")

        mock_response = httpx.Response(200, request=_DUMMY_REQUEST)
        with patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await backend.send(event, target)
            mock_post.assert_not_awaited()

        await backend.dispose()

    async def test_event_filtering_on_global_endpoint(self) -> None:
        ep = WebhookEndpoint(
            name="errors-only",
            url="https://errors.example.com/hook",
            events=["execution.failed"],
        )
        backend = WebhookBackend(endpoints=[ep])
        await backend.initialize()

        # Completed event should be filtered out
        event = _make_event(type="execution.completed")
        target = NotificationTarget(channel="webhook", target="errors-only")

        mock_response = httpx.Response(200, request=_DUMMY_REQUEST)
        with patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await backend.send(event, target)
            mock_post.assert_not_awaited()

        # Failed event should pass through
        error_event = _make_event(type="execution.failed", status="failed", error="Agent crashed")
        with patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await backend.send(error_event, target)
            mock_post.assert_awaited_once()

        await backend.dispose()

    async def test_default_secret_fallback(self) -> None:
        ep = WebhookEndpoint(name="no-secret", url="https://example.com/hook")
        backend = WebhookBackend(endpoints=[ep], default_secret="global-fallback")
        await backend.initialize()

        event = _make_event()
        target = NotificationTarget(channel="webhook", target="no-secret")

        mock_response = httpx.Response(200, request=_DUMMY_REQUEST)
        with patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await backend.send(event, target)

            headers = mock_post.call_args[1]["headers"]
            assert "X-AgentGateway-Signature" in headers

        await backend.dispose()


class TestWebhookBackendEdgeCases:
    async def test_not_initialized_raises(self) -> None:
        backend = WebhookBackend()
        event = _make_event()
        target = NotificationTarget(channel="webhook", url="https://example.com/hook")

        with pytest.raises(RuntimeError, match="not initialized"):
            await backend.send(event, target)

    async def test_no_url_or_name_skipped(self) -> None:
        backend = WebhookBackend()
        await backend.initialize()

        event = _make_event()
        target = NotificationTarget(channel="webhook")  # no url, no target

        mock_response = httpx.Response(200, request=_DUMMY_REQUEST)
        with patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await backend.send(event, target)
            mock_post.assert_not_awaited()

        await backend.dispose()

    async def test_default_payload_schema(self) -> None:
        """Default payload includes all expected fields."""
        backend = WebhookBackend()
        await backend.initialize()

        event = _make_event(
            result={"output": "summary here"},
            usage={"total_tokens": 500},
            context={"user_id": "u-1"},
        )
        target = NotificationTarget(channel="webhook", url="https://example.com/hook")

        mock_response = httpx.Response(200, request=_DUMMY_REQUEST)
        with patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await backend.send(event, target)

            payload = json.loads(mock_post.call_args[1]["content"])
            assert payload["event"] == "execution.completed"
            assert payload["execution_id"] == "exec-456"
            assert payload["agent_id"] == "test-agent"
            assert payload["status"] == "completed"
            assert payload["message"] == "Summarize quarterly report"
            assert payload["result"] == {"output": "summary here"}
            assert payload["usage"] == {"total_tokens": 500}
            assert payload["context"] == {"user_id": "u-1"}
            assert payload["duration_ms"] == 3200

        await backend.dispose()

    async def test_add_endpoint_runtime(self) -> None:
        backend = WebhookBackend()
        backend.add_endpoint(
            WebhookEndpoint(name="dynamic", url="https://dynamic.example.com/hook")
        )
        await backend.initialize()

        event = _make_event()
        target = NotificationTarget(channel="webhook", target="dynamic")

        mock_response = httpx.Response(200, request=_DUMMY_REQUEST)
        with patch.object(backend._client, "post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await backend.send(event, target)
            assert mock_post.call_args[0][0] == "https://dynamic.example.com/hook"

        await backend.dispose()
