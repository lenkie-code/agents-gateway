# Exceptions

All Agent Gateway exceptions inherit from `AgentGatewayError`. Catch this base class to handle any library error, or catch specific subclasses for fine-grained handling.

```python
from agent_gateway.exceptions import (
    AgentGatewayError,
    ConfigError,
    WorkspaceError,
    ExecutionError,
    ToolError,
    GuardrailTriggered,
    InputValidationError,
    AuthError,
    AgentMemoryError,
)
```

---

## Hierarchy

```
AgentGatewayError
├── ConfigError
├── WorkspaceError
├── ExecutionError
│   ├── ToolError
│   └── GuardrailTriggered
├── InputValidationError
├── AuthError
└── AgentMemoryError
```

---

## AgentGatewayError

```python
class AgentGatewayError(Exception)
```

Base class for all Agent Gateway errors. Catch this to handle any library-raised exception.

```python
try:
    result = await gw.invoke("my-agent", "Hello")
except AgentGatewayError as e:
    logger.error("Gateway error: %s", e)
```

---

## ConfigError

```python
class ConfigError(AgentGatewayError)
```

Raised when configuration is invalid or missing. Examples: conflicting dashboard auth settings, referencing an undefined environment variable in `gateway.yaml`.

---

## WorkspaceError

```python
class WorkspaceError(AgentGatewayError):
    path: str | None
```

Raised when a workspace file cannot be loaded or parsed.

| Attribute | Type | Description |
|-----------|------|-------------|
| `path` | `str \| None` | Path to the file that caused the error, if available. |

```python
try:
    await gw.reload()
except WorkspaceError as e:
    print(f"Failed to load workspace file: {e.path}")
```

---

## ExecutionError

```python
class ExecutionError(AgentGatewayError):
    execution_id: str | None
```

Raised when an agent execution fails.

| Attribute | Type | Description |
|-----------|------|-------------|
| `execution_id` | `str \| None` | The execution that failed, if available. |

---

## ToolError

```python
class ToolError(ExecutionError):
    tool_name: str
    execution_id: str | None
```

Raised when a tool invocation fails (unhandled exception inside the tool function).

| Attribute | Type | Description |
|-----------|------|-------------|
| `tool_name` | `str` | The name of the tool that failed. |
| `execution_id` | `str \| None` | The parent execution ID. |

```python
from agent_gateway.exceptions import ToolError

try:
    result = await gw.invoke("analyst", "Run the report")
except ToolError as e:
    print(f"Tool '{e.tool_name}' failed during execution {e.execution_id}")
```

---

## GuardrailTriggered

```python
class GuardrailTriggered(ExecutionError):
    reason: str
    partial_result: str | None
    execution_id: str | None
```

Raised when a guardrail limit is hit before the execution completes normally.

| Attribute | Type | Description |
|-----------|------|-------------|
| `reason` | `str` | Why the guardrail fired. One of `"max_tool_calls"`, `"max_iterations"`, `"timeout"`. |
| `partial_result` | `str \| None` | Any output produced before the limit was hit. May be `None` or incomplete. |
| `execution_id` | `str \| None` | The execution that was terminated. |

**Reasons:**

| Reason | Triggered by |
|--------|-------------|
| `"max_tool_calls"` | Execution reached `guardrails.max_tool_calls` tool invocations. |
| `"max_iterations"` | Execution reached `guardrails.max_iterations` LLM reasoning steps. |
| `"timeout"` | Execution exceeded `guardrails.timeout_ms` wall-clock time. |

```python
from agent_gateway.exceptions import GuardrailTriggered

try:
    result = await gw.invoke("researcher", "Analyse everything")
except GuardrailTriggered as e:
    print(f"Guardrail hit: {e.reason}")
    if e.partial_result:
        print(f"Partial output: {e.partial_result}")
```

---

## InputValidationError

```python
class InputValidationError(AgentGatewayError):
    errors: list[str]
```

Raised when structured input fails validation against an agent's input schema (JSON Schema or Pydantic model).

| Attribute | Type | Description |
|-----------|------|-------------|
| `errors` | `list[str]` | Human-readable list of validation error messages. |

```python
from agent_gateway.exceptions import InputValidationError

try:
    result = await gw.invoke("processor", "Run it", input={"amount": "not-a-number"})
except InputValidationError as e:
    for error in e.errors:
        print(f"Validation error: {error}")
```

---

## AuthError

```python
class AuthError(AgentGatewayError):
    code: str
```

Raised on authentication or authorization failure.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `code` | `str` | `"auth_error"` | Machine-readable error code. |

Common codes returned by built-in auth providers:

| Code | Meaning |
|------|---------|
| `"auth_error"` | Generic authentication failure. |
| `"missing_token"` | No `Authorization` header or token was provided. |
| `"invalid_token"` | Token format is invalid or signature verification failed. |
| `"expired_token"` | Token has expired. |
| `"insufficient_scope"` | Token lacks the required scope for this operation. |

---

## AgentMemoryError

```python
class AgentMemoryError(AgentGatewayError)
```

Base class for memory-related errors (backend failures, extraction errors, etc.). Memory failures during execution are generally logged as warnings rather than raised, so this exception most commonly surfaces during custom memory backend development or direct `MemoryManager` usage.
