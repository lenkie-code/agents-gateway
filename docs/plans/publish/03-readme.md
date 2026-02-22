---
title: "README & PyPI Landing Page"
status: pending
priority: P0
category: Documentation
date: 2026-02-22
---

# README & PyPI Landing Page

## Problem

Current README is 6 lines — just a title, badges, and one-liner. The excellent documentation in `examples/test-project/README.md` is buried and invisible to PyPI visitors. A business evaluating the library has no way to understand its value proposition.

## Files to Change

- `README.md` — Complete rewrite

## Plan

1. Write a compelling README with these sections:
   - **Tagline & badges** (PyPI version, Python versions, license, CI, coverage)
   - **What is Agent Gateway?** — 2-3 sentence value prop for businesses
   - **Features** — Bullet list: markdown-defined agents, multi-LLM support, built-in auth, dashboard, scheduling, notifications, queue-based async, telemetry, structured output, memory
   - **Quick Start** — `pip install agent-gateway` → `agent-gateway init myproject` → `agent-gateway serve` (3 commands to hello world)
   - **Define an Agent** — Show AGENT.md example
   - **Add a Tool** — Show TOOL.md + handler.py example
   - **Configuration** — Show minimal `gateway.yaml`
   - **Dashboard** — Screenshot + brief description
   - **Documentation** — Link to docs site
   - **License** — MIT
2. Add a screenshot of the dashboard to `docs/assets/` and reference in README
3. Ensure all badge URLs point to the correct repository (not personal GitHub)
