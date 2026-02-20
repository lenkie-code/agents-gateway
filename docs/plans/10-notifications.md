---
title: "Phase 2.2: Notifications (Slack, Teams, Webhook)"
type: feat
status: completed
date: 2026-02-18
depends_on: [08]
blocks: []
parent: 2026-02-18-feat-agent-gateway-framework-plan.md
---

# Phase 2.2: Notifications (Slack, Teams, Webhook)

## Goal

Outbound notifications on execution events. Slack rich blocks, Teams Adaptive Cards, generic webhooks with HMAC signing. Fire-and-forget after response returned to client.

## Prerequisites

- Phase 08 (Gateway, execution engine)

---

## Tasks

### 1. Notification Engine

**File:** `src/agent_gateway/notifications/engine.py`

- Dispatch notifications based on agent config (`notifications.on_complete`, `on_error`, etc.)
- Run as background `asyncio.create_task` — AFTER response returned to client
- Retry: 3 attempts with exponential backoff (1s, 2s, 4s)
- Notification failure: log warning, never affect execution status
- Truncate large outputs to 4KB in notification messages
- Events: `execution.completed`, `execution.failed`, `execution.timeout`, `execution.cancelled`, `approval.required`, `approval.granted`, `approval.denied`, `schedule.fired`, `schedule.failed`

### 2. Slack Adapter

**File:** `src/agent_gateway/notifications/slack.py`

- Use `slack-bolt` (optional dependency)
- Rich Block Kit formatting: agent name, status, result summary, execution link
- Graceful if `slack-bolt` not installed: log warning

### 3. Teams Adapter

**File:** `src/agent_gateway/notifications/teams.py`

- Incoming webhook via httpx POST
- Adaptive Card formatting
- No extra dependency needed

### 4. Webhook Adapter

**File:** `src/agent_gateway/notifications/webhook.py`

- POST JSON payload to configured URL
- HMAC-SHA256 signature in `X-AgentGateway-Signature` header
- Timestamp in `X-AgentGateway-Timestamp` header
- Retry on failure

---

## Tests

- Mock Slack/Teams/webhook endpoints
- Verify retry on failure (3 attempts)
- Verify HMAC signature
- Verify truncation of large outputs
- Verify fire-and-forget (response returned before notification sent)
- Verify notification failure doesn't affect execution

## Acceptance Criteria

- [ ] Slack notifications with rich formatting
- [ ] Teams notifications with Adaptive Cards
- [ ] Webhook with HMAC signing
- [ ] Retry with exponential backoff
- [ ] Fire-and-forget (non-blocking)
- [ ] Failures logged, never crash
