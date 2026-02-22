---
title: "CORS Middleware"
status: completed
priority: P0
category: Security
date: 2026-02-22
---

# CORS Middleware

## Problem

No CORS middleware configured. Browser-based clients (dashboards, SPAs, chatbots) will fail with CORS errors when calling the API. This is critical for businesses integrating agent-gateway into web applications.

## Files to Change

- `src/agent_gateway/config.py` — Add `CorsConfig` model
- `src/agent_gateway/gateway.py` — Add CORS middleware during startup
- `tests/test_integration/test_cors.py` — New test file

## Plan

1. Add `CorsConfig` to config.py:
   ```python
   class CorsConfig(BaseModel):
       enabled: bool = False
       allow_origins: list[str] = ["*"]
       allow_methods: list[str] = ["GET", "POST", "DELETE", "OPTIONS"]
       allow_headers: list[str] = ["Authorization", "Content-Type"]
       max_age: int = 3600
   ```
2. Add `cors: CorsConfig` to `GatewayConfig`
3. In `Gateway.__aenter__()`, add `CORSMiddleware` from Starlette if `cors.enabled`
4. Add a convenience method `gw.use_cors(allow_origins=["..."])` for programmatic configuration
5. Add tests verifying CORS headers on preflight and actual requests
6. Update example project to enable CORS
7. Document in configuration reference
