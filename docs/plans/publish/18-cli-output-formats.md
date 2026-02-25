---
title: "CLI Output Formats"
status: completed
priority: P2
category: DX
date: 2026-02-22
---

# CLI Output Formats

## Problem

CLI commands like `agents`, `skills`, `schedules` only output formatted tables. No `--json` or `--csv` flag for automation, scripting, or CI pipelines.

## Files to Change

- `src/agent_gateway/cli/list_cmd.py`
- `src/agent_gateway/cli/invoke.py`

## Plan

1. Add `--format` option to list commands: `table` (default), `json`, `csv`
2. Add `--format json` to `invoke` command for machine-readable output
3. Use `typer.Option` with enum for format selection
4. JSON output should match API response schemas for consistency
5. Add tests for each output format
