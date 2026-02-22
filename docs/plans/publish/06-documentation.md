---
title: "User-Facing Documentation"
status: pending
priority: P0
category: Documentation
date: 2026-02-22
---

# User-Facing Documentation

## Problem

No documentation site exists. No getting started guide, no API reference, no configuration guide, no integration guides. Businesses cannot evaluate or adopt the library without documentation.

## Files to Change

- `docs/` — New documentation structure
- `pyproject.toml` — Add docs dependencies (mkdocs)
- `mkdocs.yml` — New file

## Plan

1. Set up MkDocs with Material theme (`mkdocs-material`)
2. Create documentation structure:
   ```
   docs/
     index.md                    # Landing page
     getting-started/
       installation.md           # pip install, extras, requirements
       quickstart.md             # First agent in 5 minutes
       project-structure.md      # Workspace layout explained
     guides/
       agents.md                 # Defining agents with AGENT.md
       tools.md                  # File-based and code-based tools
       skills.md                 # Composable workflows
       configuration.md          # gateway.yaml reference
       authentication.md         # API keys, OAuth2, scopes
       persistence.md            # SQLite, PostgreSQL setup
       notifications.md          # Slack, webhooks
       scheduling.md             # Cron schedules
       memory.md                 # Agent memory system
       queue.md                  # Redis, RabbitMQ async execution
       telemetry.md              # OpenTelemetry setup
       dashboard.md              # Dashboard features, auth, theming
       context-retrieval.md      # RAG integration
       structured-output.md      # Input/output schemas
     api-reference/
       gateway.md                # Gateway class API
       configuration.md          # All config classes
       hooks.md                  # Lifecycle hooks
       exceptions.md             # Exception hierarchy
     deployment/
       production.md             # Production deployment checklist
       docker.md                 # Docker/compose setup
     changelog.md                # Version history
   ```
3. Write each page (can be iterative — start with getting-started + guides for core features)
4. Add `mkdocs.yml` with navigation, theme config, and plugins
5. Add GitHub Actions workflow to deploy docs to GitHub Pages
6. Link docs site from README
