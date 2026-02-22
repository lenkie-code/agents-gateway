---
title: "Conversation Tracing & Cost Tracking"
status: pending
priority: P0
category: Bug/UX
date: 2026-02-22
---

# Conversation Tracing & Cost Tracking

## Problem

Each chat turn creates a separate `execution_id`. On the dashboard, executions appear as isolated traces, making it impossible to view a full conversation's execution history or calculate total conversation cost.

## Root Cause

The `executions` table has no `conversation_id` / `session_id` foreign key. Each call to `gateway.chat()` generates a new `uuid4()` execution ID with no link back to the conversation.

## Files to Change

- `src/agent_gateway/persistence/domain.py` — Add `session_id` column to `ExecutionRecord`
- `src/agent_gateway/persistence/backends/sql/base.py` — Update table mapping, add FK + index
- `src/agent_gateway/gateway.py` — Pass `session_id` when creating execution records in `chat()`
- `src/agent_gateway/persistence/backends/sql/repository.py` — Add `list_by_session()`, aggregate cost queries by session
- `src/agent_gateway/api/routes/executions.py` — Add `?session_id=` filter parameter
- `src/agent_gateway/dashboard/router.py` — Group executions by conversation on detail page, show total conversation cost
- `src/agent_gateway/dashboard/models.py` — Add `ConversationDetail` view model with aggregated stats

## Plan

1. Add `session_id: str | None` field to `ExecutionRecord` domain model
2. Update SQL table mapping with nullable FK to `conversations` table + index on `session_id`
3. In `gateway.chat()`, pass the `session_id` to `_persist_execution()` so each chat turn's execution links to its conversation
4. Add `ExecutionRepository.list_by_session(session_id)` and `cost_by_session(session_id)` queries
5. Add `?session_id=` query parameter to `GET /v1/executions` endpoint
6. Update dashboard execution detail to show conversation context — link to related executions, show cumulative cost/tokens
7. Update dashboard conversation view to show total cost, token count, and execution count per conversation
8. Add tests for new queries and API parameters
9. Update example project to demonstrate conversation cost tracking
