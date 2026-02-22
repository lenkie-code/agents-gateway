# Docker Deployment

---

## Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install agents-gateway with all optional dependencies
RUN pip install --no-cache-dir "agents-gateway[all]"

# Copy your workspace (agents, skills, tools, gateway.yaml)
COPY workspace/ ./workspace/

# Optional: copy a custom entrypoint if you have a Python app.py
# COPY app.py .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health')"

CMD ["agents-gateway", "serve", "--workspace", "workspace/"]
```

If you use a custom `app.py` that creates a `Gateway` instance programmatically, replace the `CMD` with:

```dockerfile
CMD ["uvicorn", "app:gw", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### Available extras

| Extra | Includes |
|-------|---------|
| `agents-gateway[all]` | Everything below |
| `agents-gateway[postgres]` | PostgreSQL / asyncpg driver |
| `agents-gateway[sqlite]` | SQLite / aiosqlite driver |
| `agents-gateway[redis]` | Redis Streams queue |
| `agents-gateway[rabbitmq]` | RabbitMQ queue |
| `agents-gateway[oauth2]` | OAuth2/OIDC JWT validation |
| `agents-gateway[slack]` | Slack notification backend |

---

## docker-compose.yml

The example below runs the gateway with PostgreSQL and Redis. Swap `redis` for `rabbitmq` if preferred — see the commented section.

```yaml
version: "3.9"

services:
  gateway:
    build: .
    ports:
      - "8000:8000"
    environment:
      # Database
      DATABASE_URL: postgresql+asyncpg://agw:secret@postgres:5432/agw_db
      # Queue
      REDIS_URL: redis://redis:6379/0
      # Auth
      AGENT_GATEWAY_AUTH__ENABLED: "true"
      AGENT_GATEWAY_AUTH__MODE: api_key
      # API key is read from gateway.yaml using ${API_KEY}
      API_KEY: your-api-key-here
      # Dashboard
      DASHBOARD_PASSWORD: change-me
      # Secret key for session signing
      AGENT_GATEWAY_SECRET_KEY: replace-with-random-hex
      # Telemetry (optional)
      # AGENT_GATEWAY_TELEMETRY__EXPORTER: otlp
      # AGENT_GATEWAY_TELEMETRY__ENDPOINT: http://otel-collector:4317
    volumes:
      - ./workspace:/app/workspace:ro
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health')"]
      interval: 30s
      timeout: 10s
      start_period: 20s
      retries: 3

  # Optional: dedicated queue worker process
  worker:
    build: .
    command: ["agents-gateway", "serve", "--worker-only", "--workspace", "workspace/"]
    environment:
      DATABASE_URL: postgresql+asyncpg://agw:secret@postgres:5432/agw_db
      REDIS_URL: redis://redis:6379/0
      API_KEY: your-api-key-here
    volumes:
      - ./workspace:/app/workspace:ro
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: agw
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: agw_db
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agw -d agw_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Uncomment to use RabbitMQ instead of Redis
  # rabbitmq:
  #   image: rabbitmq:3-management-alpine
  #   environment:
  #     RABBITMQ_DEFAULT_USER: agw
  #     RABBITMQ_DEFAULT_PASS: secret
  #   volumes:
  #     - rabbitmq_data:/var/lib/rabbitmq
  #   healthcheck:
  #     test: ["CMD", "rabbitmq-diagnostics", "ping"]
  #     interval: 15s
  #     timeout: 10s
  #     retries: 5

volumes:
  postgres_data:
  redis_data:
  # rabbitmq_data:
```

---

## Running the Stack

```bash
# Build images and start all services
docker compose up --build -d

# Run database migrations (first deploy only, and after upgrades)
docker compose exec gateway agents-gateway db upgrade

# View gateway logs
docker compose logs -f gateway

# Scale the worker pool
docker compose up --scale worker=3 -d
```

---

## Environment Variables Reference

All `AGENT_GATEWAY_*` environment variables mirror the `gateway.yaml` structure using `__` as the nesting separator.

| Variable | Description |
|----------|-------------|
| `AGENT_GATEWAY_SERVER__PORT` | HTTP listen port (default `8000`). |
| `AGENT_GATEWAY_SERVER__WORKERS` | Number of uvicorn workers. |
| `AGENT_GATEWAY_AUTH__ENABLED` | `"true"` or `"false"`. |
| `AGENT_GATEWAY_AUTH__MODE` | `"api_key"`, `"oauth2"`, `"composite"`, or `"none"`. |
| `AGENT_GATEWAY_PERSISTENCE__BACKEND` | `"postgres"` or `"sqlite"`. |
| `AGENT_GATEWAY_PERSISTENCE__URL` | SQLAlchemy async DSN. |
| `AGENT_GATEWAY_QUEUE__BACKEND` | `"redis"`, `"rabbitmq"`, `"memory"`, or `"none"`. |
| `AGENT_GATEWAY_QUEUE__REDIS_URL` | Redis connection URL. |
| `AGENT_GATEWAY_QUEUE__RABBITMQ_URL` | RabbitMQ AMQP URL. |
| `AGENT_GATEWAY_TELEMETRY__EXPORTER` | `"otlp"`, `"console"`, or `"none"`. |
| `AGENT_GATEWAY_TELEMETRY__ENDPOINT` | OTLP collector endpoint. |
| `AGENT_GATEWAY_SECRET_KEY` | Secret for session signing and encryption. |
| `AGENT_GATEWAY_DASHBOARD__AUTH__PASSWORD` | Dashboard login password. |

Use `${VAR_NAME}` in `gateway.yaml` to reference environment variables set by Docker or your orchestrator.

---

## Volume Mounts

| Mount | Purpose |
|-------|---------|
| `./workspace:/app/workspace:ro` | Agent definitions, skills, tools, and `gateway.yaml`. Read-only in production. |

Omit `:ro` if you need hot-reload (`agents-gateway serve --reload`) during development, which writes a watcher lock file into the workspace directory.
