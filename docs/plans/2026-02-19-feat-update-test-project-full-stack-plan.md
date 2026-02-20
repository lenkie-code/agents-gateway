---
title: "Update test project to use auth, Postgres persistence, and RabbitMQ queue"
type: feat
status: completed
date: 2026-02-19
---

# Update Test Project to Use Auth, Postgres, and RabbitMQ

## Overview

Update `examples/test-project/` to showcase all recently implemented pluggable features: API key authentication, PostgreSQL persistence, and RabbitMQ queue backend. Add a Docker Compose file for infrastructure, and a new async agent with a simulated long-running tool to demonstrate queued execution.

## Problem Statement / Motivation

The test project currently uses `auth=False`, SQLite persistence, and no queue backend. Three major features have shipped (auth, persistence backends, queue backends) but the example project doesn't demonstrate them. Developers looking at the test project get no guidance on how to wire up these features in practice.

## Proposed Solution

1. Add `docker-compose.yml` with PostgreSQL and RabbitMQ (non-standard ports)
2. Update `app.py` to use fluent API: `use_api_keys()`, `use_postgres()`, `use_rabbitmq_queue()`
3. Add a `data-processor` async agent with `execution_mode: async` in frontmatter
4. Add a `process-data` code tool that simulates long-running work via `asyncio.sleep`
5. Update `gateway.yaml`, `.env.example`, README, and e2e tests

## Technical Considerations

- **Port conflicts**: Use non-standard ports (5433 for Postgres, 5673/15673 for RabbitMQ) to avoid clashing with locally running services
- **Fluent API precedence**: Fluent API (`use_*`) always wins over `gateway.yaml` config and constructor params. Remove `auth=False` from the constructor to avoid contradictory configuration
- **Optional extras**: The test project's `pyproject.toml` must declare `agent-gateway[postgres,rabbitmq]` to ensure `asyncpg` and `aio-pika` are installed (the gateway re-raises `ImportError` for missing drivers)
- **Auth middleware path exclusion**: `/v1/health` is already in `public_paths` by default. The custom `/api/health` route bypasses auth automatically (middleware only intercepts `/v1/` paths)
- **E2E test isolation**: E2E tests create their own `Gateway` instances with `auth=False` and in-memory SQLite, so they won't be affected by `app.py` changes. But adding a new agent to the workspace changes agent counts in assertions

## Acceptance Criteria

- [x] `docker compose up -d` starts PostgreSQL (port 54320) and RabbitMQ (port 56720/15680) with health checks
- [x] `app.py` uses `gw.use_api_keys()`, `gw.use_postgres()`, `gw.use_rabbitmq_queue()` via fluent API
- [x] API key is read from `AGENT_GATEWAY_API_KEY` env var
- [x] Postgres DSN is read from `POSTGRES_URL` env var
- [x] RabbitMQ URL is read from `RABBITMQ_URL` env var
- [x] `POST /v1/agents/assistant/invoke` with valid `Authorization: Bearer <key>` returns 200
- [x] `POST /v1/agents/assistant/invoke` without auth header returns 401
- [x] `GET /v1/health` works without auth (public path)
- [x] `POST /v1/agents/data-processor/invoke` returns 202 with `poll_url`
- [x] Polling `GET /v1/executions/{id}` eventually returns `completed` status
- [x] New `data-processor` agent has `execution_mode: async` in AGENT.md frontmatter
- [x] `process-data` tool simulates work with configurable `duration_seconds` (default 5)
- [x] README documents docker compose setup, auth headers, and async polling flow
- [x] E2E tests pass (agent count assertions updated)
- [x] `.env.example` contains all required env vars with placeholder values

## Implementation Plan

### Phase 1: Infrastructure (Docker Compose)

Create `examples/test-project/docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: agentgw
      POSTGRES_PASSWORD: agentgw_dev
      POSTGRES_DB: agent_gateway
    ports:
      - "5433:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agentgw"]
      interval: 5s
      timeout: 3s
      retries: 5

  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    environment:
      RABBITMQ_DEFAULT_USER: agentgw
      RABBITMQ_DEFAULT_PASS: agentgw_dev
    ports:
      - "5673:5672"
      - "15673:15672"
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "check_port_connectivity"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

**Ports chosen:**
| Service | Standard | Test Project |
|---------|----------|-------------|
| PostgreSQL | 5432 | 5433 |
| RabbitMQ AMQP | 5672 | 5673 |
| RabbitMQ Management UI | 15672 | 15673 |

### Phase 2: App Configuration (`app.py`)

Update `examples/test-project/app.py`:

```python
"""Test project for agent-gateway development."""

import asyncio
import os

import httpx
from dotenv import load_dotenv

from agent_gateway import Gateway

load_dotenv()

gw = Gateway(workspace="./workspace", title="Test Project")

# --- Pluggable backends (fluent API) ---

gw.use_postgres(
    url=os.environ.get(
        "POSTGRES_URL",
        "postgresql+asyncpg://agentgw:agentgw_dev@localhost:5433/agent_gateway",
    ),
)
gw.use_rabbitmq_queue(
    url=os.environ.get(
        "RABBITMQ_URL",
        "amqp://agentgw:agentgw_dev@localhost:5673/",
    ),
)
gw.use_api_keys(
    [
        {
            "name": "dev",
            "key": os.environ.get("AGENT_GATEWAY_API_KEY", "dev-api-key-change-me"),
            "scopes": ["*"],
        }
    ]
)

# --- Code tools ---

@gw.tool()
async def echo(message: str) -> dict:
    """Echo a message back - for testing the tool pipeline."""
    return {"echo": message}


@gw.tool()
async def add_numbers(a: float, b: float) -> dict:
    """Add two numbers - for testing structured params."""
    return {"result": a + b}


@gw.tool(
    name="process-data",
    description="Simulate a long-running data processing task. Returns a summary after processing.",
)
async def process_data(query: str, duration_seconds: float = 5.0) -> dict:
    """Simulate a long-running data processing task."""
    duration_seconds = min(max(duration_seconds, 1.0), 30.0)  # clamp 1-30s
    await asyncio.sleep(duration_seconds)
    return {
        "query": query,
        "processing_time_seconds": duration_seconds,
        "records_processed": 1_247,
        "summary": f"Processed data for query '{query}' in {duration_seconds}s. "
        "Found 1,247 matching records across 3 data sources.",
    }


# ... (existing WeatherService, search_flights, hooks, custom route unchanged)
```

Key changes:
- Remove `auth=False` from constructor
- Add `use_postgres()`, `use_rabbitmq_queue()`, `use_api_keys()` fluent calls
- Add `process-data` tool with configurable duration (clamped 1-30s)
- Read connection strings from env vars with sensible defaults matching docker-compose

### Phase 3: Async Agent Definition

Create `examples/test-project/workspace/agents/data-processor/AGENT.md`:

```markdown
---
execution_mode: async
tools:
  - process-data
---

# Data Processor

You are a data processing agent that handles long-running analytical queries.
When asked to process or analyze data, use the `process-data` tool to run
the analysis. Summarize the results clearly when processing completes.

## Rules

- Always use the `process-data` tool for data processing requests
- Include the processing time and record count in your response
- Keep responses factual and concise
```

This agent will:
- Always be queued (via RabbitMQ) because `execution_mode: async`
- Return HTTP 202 on invoke with a `poll_url` for the client
- Use the `process-data` tool which sleeps for a configurable duration

### Phase 4: Configuration Files

**Update `examples/test-project/workspace/gateway.yaml`:**

```yaml
server:
  port: 8000

model:
  default: "gemini/gemini-2.0-flash"
  temperature: 0.1

telemetry:
  enabled: true
  exporter: console
```

Remove the `auth` and `persistence` sections since the fluent API in `app.py` handles them. This avoids confusion from stale/contradictory config.

**Update `examples/test-project/.env.example`:**

```env
# LLM Provider Keys
GEMINI_API_KEY=your-gemini-api-key-here
WEATHER_API_KEY=your-open-weather-map-api-key

# Infrastructure (must match docker-compose.yml)
POSTGRES_URL=postgresql+asyncpg://agentgw:agentgw_dev@localhost:5433/agent_gateway
RABBITMQ_URL=amqp://agentgw:agentgw_dev@localhost:5673/

# Authentication
AGENT_GATEWAY_API_KEY=dev-api-key-change-me
```

**Update `examples/test-project/pyproject.toml`** — add postgres and rabbitmq extras to the dependency:

```toml
dependencies = [
    "agent-gateway[postgres,rabbitmq] @ {root:uri:../..",
    # ... other deps
]
```

### Phase 5: README Update

Update `examples/test-project/README.md` to document:

1. **Prerequisites** — add Docker requirement
2. **Setup** — add `docker compose up -d` step before running the app
3. **Curl examples** — add `Authorization: Bearer dev-api-key-change-me` header to all `/v1/` requests
4. **Async invocation example** — show the invoke -> 202 -> poll -> completed flow:

```bash
# Invoke the async data processor (returns 202 immediately)
curl -X POST http://localhost:8000/v1/agents/data-processor/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-api-key-change-me" \
  -d '{"message": "Analyze last month sales data"}'

# Poll for results (use the execution_id from the 202 response)
curl http://localhost:8000/v1/executions/{execution_id} \
  -H "Authorization: Bearer dev-api-key-change-me"
```

5. **API endpoints table** — add `/v1/executions/{id}` and `/v1/executions/{id}/cancel`
6. **Teardown** — `docker compose down` (or `docker compose down -v` to remove data)

### Phase 6: E2E Test Fixes

Update `tests/test_e2e/test_health_introspection.py`:
- `agent_count` assertion: 3 → 4
- `test_list_agents`: add `"data-processor"` to expected agent IDs

No other e2e test changes needed — e2e tests create their own Gateway with `auth=False` and in-memory SQLite, independent of `app.py`.

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `examples/test-project/docker-compose.yml` | **Create** | PostgreSQL + RabbitMQ services |
| `examples/test-project/app.py` | Edit | Add fluent API calls, process-data tool, remove auth=False |
| `examples/test-project/workspace/agents/data-processor/AGENT.md` | **Create** | Async agent definition |
| `examples/test-project/workspace/gateway.yaml` | Edit | Remove auth/persistence sections |
| `examples/test-project/.env.example` | Edit | Add infra + auth env vars, fix typo |
| `examples/test-project/README.md` | Edit | Add docker/auth/async docs |
| `examples/test-project/pyproject.toml` | Edit | Add postgres,rabbitmq extras |
| `tests/test_e2e/test_health_introspection.py` | Edit | Update agent count assertions |

## References

- Fluent API: `src/agent_gateway/gateway.py:396-528`
- Auth middleware: `src/agent_gateway/auth/middleware.py`
- Queue protocol: `src/agent_gateway/queue/protocol.py`
- Agent loading with execution_mode: `src/agent_gateway/workspace/agent.py:51,102-106`
- Async routing logic: `src/agent_gateway/api/routes/invoke.py:48-57`
- Worker pool: `src/agent_gateway/queue/worker.py`
