---
title: "Notification Delivery Confirmation"
status: completed
priority: P2
category: Reliability
date: 2026-02-22
---

# Notification Delivery Confirmation

## Problem

Notifications are fire-and-forget. Failed webhook deliveries are silently dropped with no audit trail or retry visibility. Businesses need to know if critical notifications (e.g., "agent failed on production task") were delivered.

## Files to Change

- `src/agent_gateway/notifications/models.py` — Add delivery status tracking
- `src/agent_gateway/notifications/engine.py` — Track delivery results
- `src/agent_gateway/persistence/domain.py` — Add `notification_log` table
- `src/agent_gateway/api/routes/` — Optional notifications status endpoint

## Plan

1. Add `NotificationDelivery` domain model (id, event_type, backend, target, status, attempts, last_error, timestamps)
2. Add `notification_log` table to persistence layer
3. Update `NotificationEngine` to persist delivery results after each attempt
4. Add `GET /v1/notifications?status=failed` endpoint for visibility
5. Add dashboard page showing recent notification deliveries
6. Consider adding a webhook retry button in the dashboard
