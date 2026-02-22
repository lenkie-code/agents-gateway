# Structured Output

Agent Gateway can validate and parse agent output against a schema you define. Instead of receiving a raw string, your code gets a typed Python object that you can use immediately. Input validation is also supported to reject malformed requests before they reach the agent.

## Output Schemas

### Using a Pydantic Model

Define a Pydantic model representing the expected output and pass it as `output_schema` in `ExecutionOptions`:

```python
from pydantic import BaseModel
from agent_gateway import Gateway
from agent_gateway.engine.models import ExecutionOptions

class MathResult(BaseModel):
    answer: float
    explanation: str

gw = Gateway()

result = await gw.invoke(
    "assistant",
    "What is 12 * 15?",
    options=ExecutionOptions(output_schema=MathResult),
)

assert isinstance(result.output, MathResult)
print(result.output.answer)       # 180.0
print(result.output.explanation)  # "12 multiplied by 15 equals 180."
```

The model is serialized to JSON Schema and sent to the LLM as a structured output constraint. The response is then parsed and validated against your model before being returned.

### Using a JSON Schema Dict

If you prefer not to define a Pydantic model — for example when the schema is dynamic or loaded from configuration — pass a JSON Schema dictionary directly:

```python
schema = {
    "type": "object",
    "properties": {
        "answer": {"type": "number"},
        "explanation": {"type": "string"},
    },
    "required": ["answer", "explanation"],
}

result = await gw.invoke(
    "assistant",
    "What is 12 * 15?",
    options=ExecutionOptions(output_schema=schema),
)

# result.output is a dict when a raw schema dict is provided
print(result.output["answer"])
```

The API is identical — `output_schema` accepts either a Pydantic model class or a `dict`. When a Pydantic model class is provided, `result.output` is an instance of that class. When a dict is provided, `result.output` is a plain dict.

## Input Schemas

Input schemas let you validate the data sent to an agent before execution begins. If the input does not conform to the schema, an `InputValidationError` is raised immediately without invoking the LLM.

### Defining in `AGENT.md`

Add an `input_schema` key to the frontmatter of your agent's `AGENT.md`:

```markdown
---
name: Math Assistant
input_schema:
  type: object
  properties:
    expression:
      type: string
      description: The mathematical expression to evaluate
  required:
    - expression
---

You are a mathematics assistant. Evaluate the expression provided and explain your reasoning.
```

### Defining in Code

Use `gw.set_input_schema()` to register a schema programmatically. This is useful when the schema is derived from a Pydantic model or generated at runtime:

```python
from pydantic import BaseModel
from agent_gateway import Gateway

class MathInput(BaseModel):
    expression: str

gw = Gateway()
gw.set_input_schema("math-assistant", MathInput)
```

You can pass a Pydantic model class or a JSON Schema dict to `set_input_schema`. Schemas registered in code take precedence over any `input_schema` defined in the agent's `AGENT.md` frontmatter.

### Handling Validation Errors

When input validation fails, an `InputValidationError` is raised:

```python
from agent_gateway.exceptions import InputValidationError

try:
    result = await gw.invoke("math-assistant", {"wrong_field": "hello"})
except InputValidationError as exc:
    print(exc.detail)   # Validation error details
```

`InputValidationError` is a subclass of `AgentGatewayError` and results in a `422 Unprocessable Entity` response when raised inside an API request handler.
