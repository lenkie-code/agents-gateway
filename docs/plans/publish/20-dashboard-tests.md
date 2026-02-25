---
title: "Dashboard Test Coverage"
status: completed
priority: P2
category: Testing
date: 2026-02-22
---

# Dashboard Test Coverage

## Problem

Dashboard module has only 1 test file (OAuth2). Router, auth, and models are untested. The dashboard is a key feature for businesses evaluating the library.

## Files to Change

- `tests/test_dashboard/` — New test files

## Plan

1. Add `test_auth.py` — Test password login, session cookies, logout, protected routes
2. Add `test_router.py` — Test all dashboard pages render, HTMX partial responses, error states
3. Add `test_models.py` — Test view model formatting (cost formatting, relative time, status badges)
4. Use `httpx.AsyncClient` with test Gateway instance
5. Mock persistence repositories for deterministic test data
