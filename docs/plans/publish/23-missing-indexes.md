---
title: "Missing Database Indexes"
status: pending
priority: P2
category: Performance
date: 2026-02-22
---

# Missing Database Indexes

## Problem

Several common query patterns lack indexes: `executions.created_at` (used in `cost_by_day`, `executions_by_day`), `executions.status` (used in filtering), `conversations.created_at` (used in listing).

## Files to Change

- `src/agent_gateway/persistence/backends/sql/base.py` — Add indexes to table definitions

## Plan

1. Add indexes:
   - `ix_executions_created_at` on `executions.created_at`
   - `ix_executions_status` on `executions.status`
   - `ix_conversations_created_at` on `conversations.created_at`
   - `ix_audit_log_created_at` on `audit_log.created_at`
2. Include these as part of the initial Alembic migration (plan #02)
3. For existing databases, the Alembic migration will add them
