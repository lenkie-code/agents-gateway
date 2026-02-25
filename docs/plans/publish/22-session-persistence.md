---
title: "Session Persistence"
status: completed
priority: P2
category: Infrastructure
date: 2026-02-22
---

# Session Persistence

## Problem

`SessionStore` is in-memory only. Chat sessions are lost on server restart. For businesses running production chat agents, this means users lose their conversation context on every deployment.

## Files to Change

- `src/agent_gateway/chat/session.py` — Add persistence hooks
- `src/agent_gateway/persistence/protocols.py` — Add `SessionRepository` protocol
- `src/agent_gateway/persistence/backends/sql/repository.py` — Implement SQL session storage

## Plan

1. Add `SessionRepository` protocol with `save()`, `load()`, `delete()`, `list()` methods
2. Implement SQL-backed session storage (serialize messages as JSON)
3. Update `SessionStore` to optionally back sessions with persistence:
   - On session creation/update → async persist
   - On session access (cache miss) → load from DB
   - Keep in-memory cache as hot layer, DB as cold storage
4. Add config option: `chat.persist_sessions: true` (default false for backward compat)
5. Add session restore on startup
6. Add tests for persistence round-trip
