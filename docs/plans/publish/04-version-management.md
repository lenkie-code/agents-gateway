---
title: "Version Management (Build Pipeline)"
status: completed
priority: P0
category: Packaging
date: 2026-02-22
---

# Version Management (Build Pipeline)

## Problem

`pyproject.toml` has `version = "0.0.0"` with a comment about GitVersion replacement, but no build hook actually injects the version. `__init__.py` also hardcodes `"0.0.0"`. Published packages would show version 0.0.0.

## Files to Change

- `pyproject.toml` — Configure dynamic versioning or build hook
- `src/agent_gateway/__init__.py` — Read version dynamically
- `.github/workflows/ci.yml` — Inject version at build/publish time

## Plan

1. Option A (recommended): Use `hatch-vcs` or `setuptools-scm` to derive version from git tags
   - Add `[tool.hatch.version]` with `source = "vcs"` in pyproject.toml
   - Change `version` field to dynamic: `dynamic = ["version"]`
   - Update `__init__.py` to use `importlib.metadata.version("agent-gateway")`
2. Option B: Keep GitVersion but add a CI step that writes the computed version into `pyproject.toml` before building
3. Verify version appears correctly in `pip show agent-gateway` and `agent-gateway --version`
4. Test the build locally with `uv build` and inspect the resulting wheel metadata
