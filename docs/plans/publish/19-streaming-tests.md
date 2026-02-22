---
title: "Streaming Engine Tests"
status: pending
priority: P2
category: Testing
date: 2026-02-22
---

# Streaming Engine Tests

## Problem

`src/agent_gateway/engine/streaming.py` has no dedicated test file. Streaming is a core feature (SSE for chat) and should be tested for token emission, tool call events, error events, and session locking.

## Files to Change

- `tests/test_engine/test_streaming.py` — New test file

## Plan

1. Create test file with tests for:
   - Token event emission during streaming
   - Tool call and tool result events
   - Usage event at completion
   - Error event on LLM failure
   - Session lock acquisition and release
   - Cancellation during streaming
   - Concurrent execution semaphore enforcement
2. Use `MockLLMClient` from existing conftest with streaming response support
3. Verify SSE event format (`event: type\ndata: json\n\n`)
