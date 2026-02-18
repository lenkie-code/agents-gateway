---
title: "Phase 1.1: Package Scaffolding, Configuration & Test Project"
type: feat
status: completed
date: 2026-02-18
depends_on: []
blocks: [02, 03, 04, 05, 06, 07, 08, 09]
parent: 2026-02-18-feat-agent-gateway-framework-plan.md
---

# Phase 1.1: Package Scaffolding, Configuration & Test Project

## Goal

Set up the Python package structure, configuration system, exception hierarchy, and a test project that symlinks to the library. After this phase, `uv sync` works, `uv run pytest` runs (even if tests are trivial), and the test project can `from agent_gateway import Gateway`.

## Prerequisites

- Python 3.11+ installed
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

---

## Tasks

### 1. Initialize the Project

```bash
mkdir -p /Users/vince/Src/HonesDev/agent-gateway
cd /Users/vince/Src/HonesDev/agent-gateway
git init
```

### 2. Create `pyproject.toml`

Create the root `pyproject.toml` with all dependencies, build config, tool config, and uv workspace:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent-gateway"
version = "0.1.0"
description = "An opinionated FastAPI extension for building API-first AI agent services"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
authors = [
    { name = "HonesDev" },
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Framework :: FastAPI",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
    "Typing :: Typed",
]
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "litellm>=1.40",
    "sqlalchemy>=2.0",
    "aiosqlite>=0.20",
    "python-frontmatter>=1.1",
    "python-dotenv>=1.0",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "typer>=0.12",
    "watchfiles>=0.21",
    "pydantic>=2.7",
    "pydantic-settings>=2.2",
    "opentelemetry-api>=1.24",
    "opentelemetry-sdk>=1.24",
    "opentelemetry-semantic-conventions>=0.45b",
    "apscheduler>=4.0",
]

[project.optional-dependencies]
otlp = [
    "opentelemetry-exporter-otlp-proto-grpc>=1.24",
    "opentelemetry-exporter-otlp-proto-http>=1.24",
]
slack = ["slack-bolt>=1.18"]
postgresql = ["asyncpg>=0.29", "psycopg[binary]>=3.1"]
redis = ["redis>=5.0"]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "httpx",
    "ruff>=0.4",
    "mypy>=1.10",
]
all = ["agent-gateway[otlp,slack,postgresql,redis]"]

[project.scripts]
agent-gateway = "agent_gateway.cli.main:app"

[project.urls]
Homepage = "https://github.com/honesdev/agent-gateway"
Repository = "https://github.com/honesdev/agent-gateway"

[tool.hatch.build.targets.wheel]
packages = ["src/agent_gateway"]

[tool.uv.workspace]
members = ["examples/test-project"]

[tool.ruff]
target-version = "py311"
line-length = 99

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "ASYNC"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]
```

### 3. Create Directory Structure

Create every directory and `__init__.py` file needed across the entire project. Empty `__init__.py` files are fine — they'll be filled in later phases.

```
src/agent_gateway/
├── __init__.py              # Public API: Gateway class + __version__
├── py.typed                 # PEP 561 marker (empty file)
├── exceptions.py            # Exception hierarchy
├── config.py                # Pydantic BaseSettings configuration
├── gateway.py               # Gateway(FastAPI) stub
├── workspace/
│   └── __init__.py
├── engine/
│   └── __init__.py
├── tools/
│   └── __init__.py
├── api/
│   ├── __init__.py
│   ├── routes/
│   │   └── __init__.py
│   └── middleware/
│       └── __init__.py
├── notifications/
│   └── __init__.py
├── persistence/
│   └── __init__.py
├── telemetry/
│   └── __init__.py
├── scheduler/
│   └── __init__.py
└── cli/
    └── __init__.py
```

### 4. `src/agent_gateway/__init__.py`

```python
"""Agent Gateway - an opinionated FastAPI extension for AI agent services."""

__version__ = "0.1.0"

# Gateway will be imported here once gateway.py is implemented
# from agent_gateway.gateway import Gateway
# __all__ = ["Gateway", "__version__"]
```

For now, just export the version. The `Gateway` import will be added when `gateway.py` is implemented in Phase 08.

### 5. `src/agent_gateway/py.typed`

Empty file. Signals PEP 561 compliance for type checkers.

### 6. `src/agent_gateway/exceptions.py`

```python
"""Structured exception hierarchy for Agent Gateway."""

from __future__ import annotations


class AgentGatewayError(Exception):
    """Base exception for all agent-gateway errors."""


class ConfigError(AgentGatewayError):
    """Invalid or missing configuration."""


class WorkspaceError(AgentGatewayError):
    """Error loading or parsing the workspace."""

    def __init__(self, message: str, path: str | None = None) -> None:
        self.path = path
        super().__init__(message)


class ExecutionError(AgentGatewayError):
    """Error during agent execution."""

    def __init__(self, message: str, execution_id: str | None = None) -> None:
        self.execution_id = execution_id
        super().__init__(message)


class ToolError(ExecutionError):
    """Error executing a tool."""

    def __init__(
        self,
        message: str,
        tool_name: str,
        execution_id: str | None = None,
    ) -> None:
        self.tool_name = tool_name
        super().__init__(message, execution_id)


class GuardrailTriggered(ExecutionError):
    """A guardrail limit was hit (max iterations, max tool calls, timeout)."""

    def __init__(
        self,
        reason: str,
        partial_result: str | None = None,
        execution_id: str | None = None,
    ) -> None:
        self.reason = reason
        self.partial_result = partial_result
        super().__init__(f"Guardrail triggered: {reason}", execution_id)


class AuthError(AgentGatewayError):
    """Authentication or authorization failure."""

    def __init__(self, message: str, code: str = "auth_error") -> None:
        self.code = code
        super().__init__(message)
```

### 7. `src/agent_gateway/config.py`

```python
"""Gateway configuration with Pydantic BaseSettings.

Precedence: Environment variables > gateway.yaml > defaults.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1


class ModelConfig(BaseModel):
    default: str = "gpt-4o-mini"
    temperature: float = 0.1
    max_tokens: int = 4096
    fallback: str | None = None


class GuardrailsConfig(BaseModel):
    max_tool_calls: int = 20
    max_iterations: int = 10
    timeout_ms: int = 60_000


class AuthKeyConfig(BaseModel):
    name: str
    key: str
    scopes: list[str] = Field(default_factory=lambda: ["*"])


class AuthConfig(BaseModel):
    enabled: bool = True
    mode: str = "api_key"  # api_key | custom | none
    api_keys: list[AuthKeyConfig] = Field(default_factory=list)


class SlackConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""


class TeamsConfig(BaseModel):
    enabled: bool = False
    webhook_url: str = ""


class WebhookConfig(BaseModel):
    name: str
    url: str
    secret: str = ""
    events: list[str] = Field(default_factory=list)


class NotificationsConfig(BaseModel):
    slack: SlackConfig = SlackConfig()
    teams: TeamsConfig = TeamsConfig()
    webhooks: list[WebhookConfig] = Field(default_factory=list)
    webhook_secret: str = ""


class PersistenceConfig(BaseModel):
    enabled: bool = True
    backend: str = "sqlite"  # sqlite | postgresql
    url: str = "sqlite+aiosqlite:///agent_gateway.db"


class TelemetryConfig(BaseModel):
    enabled: bool = True
    service_name: str = "agent-gateway"
    exporter: str = "console"  # console | otlp | none
    endpoint: str = "http://localhost:4317"
    protocol: str = "grpc"  # grpc | http
    sample_rate: float = 1.0


class QueueConfig(BaseModel):
    backend: str = "memory"  # memory | redis
    url: str = "redis://localhost:6379"


class GatewayConfig(BaseSettings):
    """Root configuration for the Agent Gateway.

    Loaded from gateway.yaml, overridden by environment variables
    prefixed with AGENT_GATEWAY_.
    """

    model_config = {"env_prefix": "AGENT_GATEWAY_", "env_nested_delimiter": "__"}

    server: ServerConfig = ServerConfig()
    model: ModelConfig = ModelConfig()
    guardrails: GuardrailsConfig = GuardrailsConfig()
    auth: AuthConfig = AuthConfig()
    notifications: NotificationsConfig = NotificationsConfig()
    persistence: PersistenceConfig = PersistenceConfig()
    telemetry: TelemetryConfig = TelemetryConfig()
    queue: QueueConfig = QueueConfig()
    context: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> GatewayConfig:
        """Load config from a YAML file, with defaults for missing fields."""
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)

    @classmethod
    def load(cls, workspace_path: Path) -> GatewayConfig:
        """Load config from workspace/gateway.yaml if it exists."""
        yaml_path = workspace_path / "gateway.yaml"
        return cls.from_yaml(yaml_path)
```

### 8. `src/agent_gateway/gateway.py` (Stub)

Minimal stub so `from agent_gateway import Gateway` works. Will be fully implemented in Phase 08.

```python
"""Gateway - FastAPI subclass for AI agent services."""

from __future__ import annotations

from fastapi import FastAPI


class Gateway(FastAPI):
    """An opinionated FastAPI extension for building API-first AI agent services.

    Subclasses FastAPI directly. Everything you can do with a FastAPI app,
    you can do with a Gateway.
    """

    def __init__(
        self,
        workspace: str = "./workspace",
        auth: bool | None = True,
        reload: bool = False,
        **fastapi_kwargs: object,
    ) -> None:
        self._workspace_path = workspace
        self._auth_enabled = auth
        self._reload_enabled = reload
        super().__init__(**fastapi_kwargs)

    def run(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        **kwargs: object,
    ) -> None:
        """Start the gateway server using uvicorn."""
        import uvicorn

        uvicorn.run(self, host=host, port=port, **kwargs)  # type: ignore[arg-type]
```

Update `src/agent_gateway/__init__.py` to export it:

```python
"""Agent Gateway - an opinionated FastAPI extension for AI agent services."""

__version__ = "0.1.0"

from agent_gateway.gateway import Gateway

__all__ = ["Gateway", "__version__"]
```

### 9. `src/agent_gateway/cli/main.py` (Stub)

Minimal Typer entry point so the `agent-gateway` script works:

```python
"""Agent Gateway CLI."""

import typer

app = typer.Typer(
    name="agent-gateway",
    help="An opinionated FastAPI extension for building API-first AI agent services.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Show the agent-gateway version."""
    from agent_gateway import __version__

    typer.echo(f"agent-gateway {__version__}")
```

### 10. Test Fixtures

Create a minimal test workspace:

**`tests/conftest.py`:**

```python
"""Shared test fixtures for agent-gateway."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_WORKSPACE = FIXTURES_DIR / "workspace"


@pytest.fixture
def fixture_workspace() -> Path:
    """Path to the test fixture workspace."""
    return FIXTURE_WORKSPACE


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory with standard structure."""
    agents = tmp_path / "agents"
    skills = tmp_path / "skills"
    tools = tmp_path / "tools"
    agents.mkdir()
    skills.mkdir()
    tools.mkdir()
    return tmp_path
```

**`tests/fixtures/workspace/agents/test-agent/AGENT.md`:**

```markdown
# Test Agent

You are a helpful test agent. Answer questions clearly and concisely.

## Rules

- Keep responses short
- Use plain language
```

**`tests/fixtures/workspace/skills/test-skill/SKILL.md`:**

```markdown
---
name: test-skill
description: A test skill for unit tests
tools:
  - echo
---

# Test Skill

When asked to test something, use the `echo` tool to echo the input back.
```

**`tests/fixtures/workspace/tools/test-tool/TOOL.md`:**

```markdown
---
name: echo
description: Echo the input back
type: function
parameters:
  message:
    type: string
    description: "Message to echo back"
    required: true
---

# Echo Tool

Returns the input message unchanged. Used for testing.
```

**`tests/fixtures/workspace/gateway.yaml`:**

```yaml
server:
  host: "127.0.0.1"
  port: 8000

model:
  default: "gpt-4o-mini"
  temperature: 0.1

auth:
  enabled: false

persistence:
  enabled: false

telemetry:
  enabled: false
```

### 11. Initial Tests

**`tests/test_config.py`:**

```python
"""Tests for gateway configuration."""

from __future__ import annotations

from pathlib import Path

from agent_gateway.config import GatewayConfig


class TestGatewayConfig:
    def test_default_config(self) -> None:
        config = GatewayConfig()
        assert config.server.port == 8000
        assert config.model.default == "gpt-4o-mini"
        assert config.guardrails.max_iterations == 10
        assert config.guardrails.max_tool_calls == 20
        assert config.guardrails.timeout_ms == 60_000

    def test_load_from_yaml(self, fixture_workspace: Path) -> None:
        config = GatewayConfig.load(fixture_workspace)
        assert config.server.host == "127.0.0.1"
        assert config.auth.enabled is False
        assert config.persistence.enabled is False

    def test_load_missing_yaml(self, tmp_path: Path) -> None:
        config = GatewayConfig.load(tmp_path)
        assert config.server.port == 8000  # defaults

    def test_env_override(self, monkeypatch: object) -> None:
        import os
        os.environ["AGENT_GATEWAY_SERVER__PORT"] = "9000"
        try:
            config = GatewayConfig()
            assert config.server.port == 9000
        finally:
            del os.environ["AGENT_GATEWAY_SERVER__PORT"]


class TestModelConfig:
    def test_defaults(self) -> None:
        config = GatewayConfig()
        assert config.model.temperature == 0.1
        assert config.model.max_tokens == 4096
        assert config.model.fallback is None


class TestGuardrailsConfig:
    def test_defaults(self) -> None:
        config = GatewayConfig()
        assert config.guardrails.max_tool_calls == 20
        assert config.guardrails.max_iterations == 10
        assert config.guardrails.timeout_ms == 60_000
```

**`tests/test_exceptions.py`:**

```python
"""Tests for exception hierarchy."""

from agent_gateway.exceptions import (
    AgentGatewayError,
    AuthError,
    ConfigError,
    ExecutionError,
    GuardrailTriggered,
    ToolError,
    WorkspaceError,
)


class TestExceptionHierarchy:
    def test_all_inherit_from_base(self) -> None:
        assert issubclass(ConfigError, AgentGatewayError)
        assert issubclass(WorkspaceError, AgentGatewayError)
        assert issubclass(ExecutionError, AgentGatewayError)
        assert issubclass(ToolError, ExecutionError)
        assert issubclass(GuardrailTriggered, ExecutionError)
        assert issubclass(AuthError, AgentGatewayError)

    def test_workspace_error_has_path(self) -> None:
        err = WorkspaceError("bad file", path="/workspace/agents/foo/AGENT.md")
        assert err.path == "/workspace/agents/foo/AGENT.md"
        assert "bad file" in str(err)

    def test_tool_error_has_tool_name(self) -> None:
        err = ToolError("timeout", tool_name="companies-house-check", execution_id="exec_123")
        assert err.tool_name == "companies-house-check"
        assert err.execution_id == "exec_123"

    def test_guardrail_triggered(self) -> None:
        err = GuardrailTriggered(reason="max_iterations", partial_result="partial...")
        assert err.reason == "max_iterations"
        assert err.partial_result == "partial..."
        assert "Guardrail triggered" in str(err)

    def test_auth_error_has_code(self) -> None:
        err = AuthError("invalid key", code="invalid_api_key")
        assert err.code == "invalid_api_key"
```

**`tests/test_gateway_stub.py`:**

```python
"""Tests for the Gateway stub."""

from agent_gateway import Gateway, __version__


class TestGatewayStub:
    def test_gateway_is_fastapi(self) -> None:
        from fastapi import FastAPI
        gw = Gateway()
        assert isinstance(gw, FastAPI)

    def test_gateway_default_params(self) -> None:
        gw = Gateway()
        assert gw._workspace_path == "./workspace"
        assert gw._auth_enabled is True
        assert gw._reload_enabled is False

    def test_gateway_custom_params(self) -> None:
        gw = Gateway(workspace="./my-agents", auth=False, reload=True, title="Test")
        assert gw._workspace_path == "./my-agents"
        assert gw._auth_enabled is False
        assert gw._reload_enabled is True
        assert gw.title == "Test"

    def test_version(self) -> None:
        assert __version__ == "0.1.0"
```

### 12. Test Project Setup

**`examples/test-project/pyproject.toml`:**

```toml
[project]
name = "test-project"
version = "0.1.0"
description = "Test project for agent-gateway development"
requires-python = ">=3.11"
dependencies = [
    "agent-gateway",
]

[tool.uv.sources]
agent-gateway = { workspace = true }
```

**`examples/test-project/app.py`:**

```python
"""Test project for agent-gateway development."""

from agent_gateway import Gateway

gw = Gateway(workspace="./workspace", auth=False, title="Test Project")


@gw.tool()
async def echo(message: str) -> dict:
    """Echo a message back - for testing the tool pipeline."""
    return {"echo": message}


@gw.tool()
async def add_numbers(a: float, b: float) -> dict:
    """Add two numbers - for testing structured params."""
    return {"result": a + b}


@gw.get("/api/health")
async def health():
    return {"status": "ok", "project": "test-project"}


if __name__ == "__main__":
    gw.run(port=8000)
```

**`examples/test-project/.env.example`:**

```bash
# LLM Provider Keys (at least one required)
# GEMINI_API_KEY=AIzaSy...
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...

# Gateway
AGENT_GATEWAY_AUTH__ENABLED=false
```

**`examples/test-project/workspace/gateway.yaml`:**

```yaml
server:
  port: 8000

model:
  default: "gpt-4o-mini"
  temperature: 0.1

auth:
  enabled: false

persistence:
  enabled: true
  backend: sqlite
  url: "sqlite+aiosqlite:///test_project.db"

telemetry:
  enabled: true
  exporter: console
```

**`examples/test-project/workspace/agents/AGENTS.md`:**

```markdown
# System Context

You are an AI agent running inside the Agent Gateway test project.
Keep responses concise and helpful.
```

**`examples/test-project/workspace/agents/assistant/AGENT.md`:**

```markdown
# Assistant Agent

You are a helpful assistant for testing the agent-gateway framework.

## Capabilities

- Echo messages back using the `echo` tool
- Perform arithmetic using the `add_numbers` tool
- Follow multi-step workflows defined in skills

## Rules

- Always use tools when they are relevant to the request
- Keep responses concise
```

**`examples/test-project/workspace/agents/assistant/SOUL.md`:**

```markdown
# SOUL

Friendly, concise, and helpful.

- Use plain language
- Be direct
- Keep responses under 200 words unless more detail is requested
```

**`examples/test-project/workspace/agents/assistant/CONFIG.md`:**

```markdown
---
skills:
  - math-workflow
tools:
  - echo
  - add-numbers
  - http-example
---

# Assistant Configuration

Uses the default model from gateway.yaml.
Has access to echo, add_numbers tools and the math-workflow skill.
```

**`examples/test-project/workspace/agents/scheduled-reporter/AGENT.md`:**

```markdown
# Scheduled Reporter

You generate periodic summary reports. When invoked, provide a brief
status report with the current date and a summary of system health.
```

**`examples/test-project/workspace/agents/scheduled-reporter/CONFIG.md`:**

```markdown
---
schedules:
  - name: daily-report
    cron: "0 9 * * 1-5"
    message: "Generate a daily status report"
    enabled: false
    timezone: "Europe/London"
---

# Scheduled Reporter Configuration

Runs daily at 9am UK time on weekdays (disabled by default for testing).
```

**`examples/test-project/workspace/skills/math-workflow/SKILL.md`:**

```markdown
---
name: math-workflow
description: Multi-step arithmetic workflow for testing
tools:
  - add-numbers
---

# Math Workflow

When asked to perform multi-step arithmetic:

1. Break the problem into individual addition operations
2. Use `add_numbers` for each step
3. Combine results and present the final answer

## Example

"What is 1 + 2 + 3?"
- Step 1: add_numbers(1, 2) = 3
- Step 2: add_numbers(3, 3) = 6
- Answer: 6
```

**`examples/test-project/workspace/tools/http-example/TOOL.md`:**

```markdown
---
name: http-example
description: Test HTTP tool that calls httpbin.org
type: http
http:
  method: GET
  url: "https://httpbin.org/get?q=${query}"
  timeout_ms: 5000
parameters:
  query:
    type: string
    description: "Query string to send"
    required: true
---

# HTTP Example Tool

Calls httpbin.org to test HTTP tool execution. Returns request details.
```

### 13. Root Files

**`.gitignore`:**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
*.egg

# Virtual environments
.venv/
venv/

# uv
uv.lock

# IDE
.idea/
.vscode/
*.swp
*.swo

# Environment
.env
!.env.example

# Database
*.db

# OS
.DS_Store
Thumbs.db

# Testing
.coverage
htmlcov/
.pytest_cache/
.mypy_cache/
```

**`Makefile`:**

```makefile
.PHONY: dev test lint check typecheck

dev:  ## Run the test project
	uv run --directory examples/test-project python app.py

test:  ## Run library tests
	uv run pytest

lint:  ## Lint with ruff
	uv run ruff check src/ tests/

typecheck:  ## Type check with mypy
	uv run mypy src/

check: lint typecheck test  ## Run all checks
```

### 14. Sync & Verify

After creating all files:

```bash
cd /Users/vince/Src/HonesDev/agent-gateway
uv sync
uv run pytest
uv run ruff check src/ tests/
```

---

## Files Created (Complete List)

```
pyproject.toml
Makefile
.gitignore
src/agent_gateway/__init__.py
src/agent_gateway/py.typed
src/agent_gateway/exceptions.py
src/agent_gateway/config.py
src/agent_gateway/gateway.py
src/agent_gateway/workspace/__init__.py
src/agent_gateway/engine/__init__.py
src/agent_gateway/tools/__init__.py
src/agent_gateway/api/__init__.py
src/agent_gateway/api/routes/__init__.py
src/agent_gateway/api/middleware/__init__.py
src/agent_gateway/notifications/__init__.py
src/agent_gateway/persistence/__init__.py
src/agent_gateway/telemetry/__init__.py
src/agent_gateway/scheduler/__init__.py
src/agent_gateway/cli/__init__.py
src/agent_gateway/cli/main.py
tests/conftest.py
tests/test_config.py
tests/test_exceptions.py
tests/test_gateway_stub.py
tests/fixtures/workspace/gateway.yaml
tests/fixtures/workspace/agents/test-agent/AGENT.md
tests/fixtures/workspace/skills/test-skill/SKILL.md
tests/fixtures/workspace/tools/test-tool/TOOL.md
examples/test-project/pyproject.toml
examples/test-project/app.py
examples/test-project/.env.example
examples/test-project/workspace/gateway.yaml
examples/test-project/workspace/agents/AGENTS.md
examples/test-project/workspace/agents/assistant/AGENT.md
examples/test-project/workspace/agents/assistant/SOUL.md
examples/test-project/workspace/agents/assistant/CONFIG.md
examples/test-project/workspace/agents/scheduled-reporter/AGENT.md
examples/test-project/workspace/agents/scheduled-reporter/CONFIG.md
examples/test-project/workspace/skills/math-workflow/SKILL.md
examples/test-project/workspace/tools/http-example/TOOL.md
```

## Acceptance Criteria

- [x] `uv sync` completes without errors
- [x] `uv run pytest` passes all tests (config, exceptions, gateway stub)
- [x] `uv run ruff check src/ tests/` passes
- [x] `from agent_gateway import Gateway, __version__` works
- [x] `from agent_gateway.exceptions import *` works
- [x] `from agent_gateway.config import GatewayConfig` works
- [x] `GatewayConfig.load(Path("tests/fixtures/workspace"))` loads correctly
- [x] Test project can import: `cd examples/test-project && uv run python -c "from agent_gateway import Gateway; print('ok')"`
- [x] `make test` works
- [x] `make lint` works
