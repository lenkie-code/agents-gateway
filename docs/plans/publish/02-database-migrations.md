---
title: "Database Migration Strategy"
status: pending
priority: P0
category: Infrastructure
date: 2026-02-22
---

# Database Migration Strategy

## Problem

Currently uses `metadata.create_all()` which only creates new tables/columns. Cannot handle column renames, type changes, constraint modifications, or data migrations. Users upgrading the library will have no way to evolve their schema.

## Files to Change

- `pyproject.toml` — Add `alembic` dependency
- `src/agent_gateway/persistence/migrations/` — New directory with Alembic config
- `src/agent_gateway/persistence/backends/sql/base.py` — Replace `create_all()` with Alembic runner
- `src/agent_gateway/cli/main.py` — Add `agent-gateway db upgrade` / `db downgrade` commands

## Plan

1. Add `alembic` as a core dependency in `pyproject.toml`
2. Create `src/agent_gateway/persistence/migrations/` with:
   - `alembic.ini` template (shipped with the package)
   - `env.py` configured to use the user's `persistence.url` from gateway config
   - `versions/` directory with initial migration creating all current tables
3. Update `SqlBackendBase.initialize()` to run Alembic `upgrade head` instead of `create_all()`
4. Add CLI commands:
   - `agent-gateway db upgrade [revision]` — Apply migrations
   - `agent-gateway db downgrade [revision]` — Roll back migrations
   - `agent-gateway db current` — Show current schema version
   - `agent-gateway db history` — Show migration history
5. Create the initial migration script capturing the current schema as baseline
6. Document the migration workflow in user docs (new installs auto-migrate; upgrades require `agent-gateway db upgrade`)
7. Add tests for migration up/down paths
8. Update example project README with migration instructions
