---
title: "PyPI Publish Workflow"
status: pending
priority: P1
category: CI/CD
date: 2026-02-22
---

# PyPI Publish Workflow

## Problem

CI pipeline tags versions but has no step to build and upload to PyPI. The library cannot be installed via `pip install agent-gateway`.

## Files to Change

- `.github/workflows/publish.yml` — New workflow
- `pyproject.toml` — Verify build metadata

## Plan

1. Create `.github/workflows/publish.yml` triggered on git tag push (`v*`)
2. Steps:
   - Checkout code
   - Set up Python + uv
   - Inject version from tag
   - Build with `uv build`
   - Publish to PyPI with `twine upload` or `uv publish` using `PYPI_TOKEN` secret
3. Add a manual trigger option for publishing pre-releases
4. Test with TestPyPI first before real publish
5. Add PyPI badge to README once first version is published
