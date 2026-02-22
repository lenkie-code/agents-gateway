# Project Structure

Agent Gateway projects are organized around a **workspace directory**. The workspace is a folder of Markdown and Python files that define your agents, skills, and tools. The Gateway reads this directory at startup and registers everything automatically.

## Workspace Layout

```
workspace/
├── gateway.yaml               # Server and application configuration
├── agents/
│   ├── AGENTS.md              # Root system prompt (optional, shared across all agents)
│   ├── BEHAVIOR.md            # Root behavior prompt (optional)
│   └── <agent-id>/
│       ├── AGENT.md           # Required — agent definition
│       ├── BEHAVIOR.md        # Optional — behavioral guardrails
│       └── context/           # Optional — static context files (.md)
├── skills/
│   └── <skill-id>/
│       └── SKILL.md           # Skill definition with tools and workflow steps
└── tools/
    └── <tool-id>/
        ├── TOOL.md            # Tool definition with parameters
        └── handler.py         # Python handler function
```

## Naming Rules

Directory names for agents, skills, and tools must match the pattern:

```
^[a-z0-9][a-z0-9_-]{0,63}$
```

Names must start with a lowercase letter or digit, contain only lowercase letters, digits, hyphens, and underscores, and be at most 64 characters. The directory name becomes the resource identifier used in API paths (e.g., `workspace/agents/my-agent/` is served at `/v1/agents/my-agent`).

## File Reference

### `gateway.yaml`

The central configuration file for the application. All server, model, authentication, persistence, and integration settings live here:

```yaml
server:
  host: 0.0.0.0
  port: 8000

model:
  provider: openai
  name: gpt-4o

auth:
  backend: none

persistence:
  backend: sqlite
  url: sqlite+aiosqlite:///./data.db
```

See the configuration reference for the full list of supported keys.

### `agents/AGENTS.md`

An optional Markdown file whose body is prepended as a shared system prompt to every agent in the workspace. Use it for organization-wide instructions that apply universally.

### `agents/BEHAVIOR.md`

An optional root behavior prompt applied to all agents. Typically used for global guardrails such as tone, safety constraints, or output formatting rules.

### `agents/<agent-id>/AGENT.md`

Required for every agent. The YAML frontmatter configures the agent; the Markdown body is its system prompt.

```markdown
---
description: A billing support specialist.
skills:
  - lookup-invoice
tools:
  - send-email
memory: true
---

You are a billing support agent. Help customers with invoice questions and payment issues.
Always confirm the customer's account before sharing any billing details.
```

### `agents/<agent-id>/BEHAVIOR.md`

Optional. Contains behavioral guardrails that are merged with the root behavior prompt. Use this for agent-specific constraints without modifying the shared root file.

### `agents/<agent-id>/context/`

Optional directory of `.md` files that are injected as static context into the agent's prompt at runtime. Useful for product documentation, FAQ content, or reference data that does not change between requests.

### `skills/<skill-id>/SKILL.md`

Defines a reusable skill — a named capability composed of one or more tools and an optional workflow. Skills can be attached to multiple agents via their frontmatter.

### `tools/<tool-id>/TOOL.md`

Declares a file-based tool: its description, input parameters, and output schema. The tool's logic lives in `handler.py` alongside it.

### `tools/<tool-id>/handler.py`

A Python module containing a function named `handler` that the Gateway calls when the tool is invoked:

```python
def handler(city: str) -> str:
    return f"It is sunny and 22°C in {city}."
```

## Programmatic Configuration

`gateway.yaml` covers most use cases, but you can configure the Gateway entirely in Python when you need dynamic setup or tighter integration with existing application code:

```python
from agent_gateway import Gateway

gw = Gateway(workspace="./workspace")

gw.configure_model(provider="openai", name="gpt-4o")
gw.configure_persistence(backend="postgres", url="postgresql+asyncpg://...")
gw.configure_auth(backend="oauth2", issuer="https://auth.example.com")

@gw.tool(name="get_weather", description="Get the current weather for a city.")
def get_weather(city: str) -> str:
    return f"Sunny in {city}."

if __name__ == "__main__":
    gw.run()
```

Settings applied in Python take precedence over `gateway.yaml`.

!!! note
    You do not need both `gateway.yaml` and Python configuration. Use whichever approach suits your project. Most projects start with `gateway.yaml` and graduate to Python configuration when they need conditional logic or environment-specific overrides.
