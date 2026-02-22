# Installation

Agent Gateway requires **Python 3.11 or later**.

## Basic Install

Install the core package from PyPI:

```bash
pip install agents-gateway
```

The core package includes the Gateway framework, workspace loader, and built-in HTTP API. Optional integrations are available as extras.

## Extras

Install extras alongside the core package using the `[extra]` syntax:

```bash
pip install agents-gateway[all]
```

The `all` extra installs every optional dependency. To keep your environment lean, install only what you need:

| Extra | What it adds |
|---|---|
| `sqlite` | SQLite persistence backend |
| `postgres` | PostgreSQL persistence backend (asyncpg) |
| `redis` | Redis queue and cache backend |
| `rabbitmq` | RabbitMQ message queue backend |
| `oauth2` | OAuth2 / JWT authentication |
| `slack` | Slack notification backend |
| `webhooks` | Outbound webhook notifications |
| `dashboard` | Built-in monitoring dashboard |
| `otlp` | OpenTelemetry / OTLP tracing and metrics |
| `docs` | Enhanced API documentation (ReDoc, Scalar) |

Install multiple extras at once:

```bash
pip install "agents-gateway[postgres,redis,oauth2]"
```

## Using uv

If you use [uv](https://docs.astral.sh/uv/), add Agent Gateway to your project:

```bash
uv add "agents-gateway[all]"
```

Or with specific extras:

```bash
uv add "agents-gateway[postgres,redis,oauth2]"
```

## Verify the Installation

After installing, confirm the CLI is available:

```bash
agents-gateway version
```

You should see the installed version printed to stdout.

!!! tip
    If the `agents-gateway` command is not found, ensure the Python environment where the package was installed is on your `PATH`. When using `uv`, prefer `uv run agents-gateway version` to run within the managed environment.
