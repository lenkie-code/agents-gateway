# Tools

Tools are functions the LLM can call during an agent execution. Agent Gateway supports two ways to define tools: file-based tools defined in Markdown and Python handler files, and code-based tools registered via the `@gw.tool` decorator.

## File-based tools

File-based tools live under `workspace/tools/` — one directory per tool:

```
workspace/
  tools/
    search-hotels/
      TOOL.md       # Tool definition (name, description, parameters)
      handler.py    # Python implementation
    send-email/
      TOOL.md
      handler.py
```

### TOOL.md

The `TOOL.md` file defines the tool's metadata and parameter schema in its YAML frontmatter. The Markdown body provides additional instructions for the LLM about how to use the tool.

```markdown
---
name: search-hotels
description: Search for available hotels at a destination for given dates.
parameters:
  destination:
    type: string
    description: The city to search hotels in
    required: true
  checkin:
    type: string
    description: Check-in date (YYYY-MM-DD)
    required: true
  checkout:
    type: string
    description: Check-out date (YYYY-MM-DD)
    required: true
  max_price_usd:
    type: number
    description: Maximum price per night in USD
    required: false
    default: 500
  stars:
    type: integer
    description: Minimum star rating
    required: false
    enum: [1, 2, 3, 4, 5]
---

Returns a list of available hotels sorted by price. Always include the
checkin and checkout dates — the tool requires both.
```

#### Parameter fields

| Field | Required | Description |
|---|---|---|
| `type` | no | JSON Schema type: `string`, `number`, `integer`, `boolean`, `array`, `object`. Defaults to `string` |
| `description` | no | Description sent to the LLM |
| `required` | no | Whether the parameter is required. Defaults to `false` |
| `enum` | no | List of allowed values |
| `default` | no | Default value when parameter is omitted |

#### Tool permissions

Restrict which agents can use a tool and whether human approval is required:

```yaml
permissions:
  allowed_agents:
    - travel-planner
    - booking-assistant
  require_approval: false
```

`allowed_agents` — list of agent IDs that may call this tool. When omitted, all agents can use the tool.

`require_approval` — when `true`, the gateway pauses execution and waits for explicit approval before calling the tool. Defaults to `false`.

### handler.py

The handler implements the tool's logic. The gateway loads `handler.py` at runtime and calls the `handle` function:

```python
# workspace/tools/search-hotels/handler.py
from agent_gateway.engine.models import ToolContext

async def handle(arguments: dict, context: ToolContext) -> str:
    destination = arguments.get("destination", "")
    checkin = arguments.get("checkin", "")
    checkout = arguments.get("checkout", "")

    # Call your actual data source here
    hotels = [
        {"name": "Grand Hotel", "price_usd": 180, "stars": 4},
        {"name": "City Inn", "price_usd": 95, "stars": 3},
    ]

    return str({"hotels": hotels, "destination": destination})
```

The `handle` function receives all parameters as a `dict` and a `ToolContext`. Both sync and async implementations are supported — the gateway awaits async functions and runs sync functions in a thread pool.

Return value should be a `str`, but the gateway will coerce other types by calling `str()` on the result.

## Code-based tools

Register tools directly in Python using the `@gw.tool` decorator. Code tools are defined alongside your application code and do not require a file in the workspace.

### Simple decorator

When a function has a clear docstring, the name and description are inferred automatically:

```python
@gw.tool()
async def echo(message: str) -> dict:
    """Echo a message back - for testing the tool pipeline."""
    return {"echo": message}
```

- Tool name: `echo` (from function name, underscores become hyphens: `echo`)
- Description: taken from the docstring

### Full decorator

Specify name, description, and permissions explicitly:

```python
@gw.tool(
    name="search-flights",
    description="Search for available flights between two cities on a given date.",
    allowed_agents=["travel-planner"],
    require_approval=False,
)
async def search_flights(origin: str, destination: str, date: str) -> dict:
    return {
        "origin": origin,
        "destination": destination,
        "flights": [
            {"airline": "SkyWay", "departure": "08:00", "price_usd": 320},
        ],
    }
```

You can also register a bound method or any callable:

```python
weather = WeatherService()
gw.tool(name="get-weather")(weather.get_weather)
```

### Parameter schema inference

The gateway infers the tool's JSON Schema from the function signature in this priority order:

1. **Explicit dict** — pass a `parameters_schema` dict to the decorator
2. **Pydantic model** — a single parameter typed as a `BaseModel` subclass
3. **`Annotated` types** — use `Annotated[type, "description"]` for per-parameter descriptions
4. **Bare type hints** — `str`, `int`, `float`, `bool` map to their JSON Schema equivalents

```python
from typing import Annotated

@gw.tool()
async def add_numbers(
    a: Annotated[float, "First number"],
    b: Annotated[float, "Second number"],
) -> dict:
    """Add two numbers."""
    return {"result": a + b}
```

Default values in the function signature are respected — parameters with defaults are not marked as required.

### ToolContext injection

If your tool function accepts a parameter named `context` typed as `ToolContext`, the gateway injects it automatically at call time. It is not exposed to the LLM as a parameter.

```python
from agent_gateway.engine.models import ToolContext

@gw.tool(name="audit-action")
async def audit_action(action: str, context: ToolContext) -> str:
    """Record an auditable action."""
    print(f"exec={context.execution_id} agent={context.agent_id} caller={context.caller_identity}")
    return f"Recorded: {action}"
```

`ToolContext` fields:

| Field | Type | Description |
|---|---|---|
| `execution_id` | `str` | Unique ID for the current agent execution |
| `agent_id` | `str` | ID of the agent that called the tool |
| `caller_identity` | `str \| None` | Authenticated subject from the API request |
| `metadata` | `dict` | Arbitrary metadata dict |

## Tool resolution and precedence

When a tool name exists as both a file-based tool and a code tool, the code tool takes precedence. A log message is emitted to indicate the override.

Agents do not have access to tools directly. Tools must be declared in a skill's `tools:` list, and that skill must be referenced in the agent's `skills:` list. See [Skills](skills.md) for details.
