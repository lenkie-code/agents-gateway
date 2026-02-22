# Skills

Skills are composable workflow units that group tools together and provide the LLM with instructions for using them. An agent gains access to tools exclusively through the skills listed in its `AGENT.md` frontmatter.

## Directory structure

```
workspace/
  skills/
    travel-planning/
      SKILL.md
    email-tools/
      SKILL.md
    math-workflow/
      SKILL.md
```

Each skill is a directory under `workspace/skills/` containing a `SKILL.md` file. The directory name is the skill ID used in agent configuration.

## SKILL.md structure

```markdown
---
name: travel-planning
description: End-to-end travel research and planning
tools:
  - get-weather
  - search-flights
  - search-hotels
  - search-activities
---

# Travel Planning

When planning a trip:

1. Check **weather** at the destination for the travel dates
2. Search for **flights** between origin and destination
3. Search for **hotels** at the destination
4. Search for **activities** and attractions
5. Combine all results into a comprehensive travel plan with budget breakdown
```

The Markdown body is injected into the agent's prompt to guide the LLM on how to use the skill's tools. Think of it as usage instructions for the LLM.

## Frontmatter reference

| Field | Required | Description |
|---|---|---|
| `name` | no | Display name for the skill. Defaults to the directory name |
| `description` | yes | Description of what this skill does |
| `tools` | no | List of tool IDs this skill makes available |
| `steps` | no | Ordered workflow steps (see below) |

## Referencing skills from agents

List skill IDs in the agent's `AGENT.md` frontmatter:

```yaml
skills:
  - travel-planning
  - general-tools
```

The agent will have access to all tools declared across all listed skills. Tool lists are deduplicated — listing the same tool ID in multiple skills has no effect.

## Workflow steps

Skills can define an explicit multi-step execution plan using the `steps:` key. Each step in the plan executes in sequence. Steps can call a single tool, fan out to multiple tools in parallel, or invoke the LLM directly without a tool call.

```yaml
steps:
  - name: fetch-weather
    tool: get-weather
    input:
      destination: "$.input.destination"
      date: "$.input.departure_date"

  - name: fetch-flights-and-hotels
    tools:
      - tool: search-flights
        input:
          origin: "$.input.origin"
          destination: "$.input.destination"
      - tool: search-hotels
        input:
          destination: "$.input.destination"

  - name: summarize
    prompt: "Summarize the travel options in a concise plan."
    input:
      weather: "$.steps.fetch-weather.output"
      flights: "$.steps.fetch-flights-and-hotels.output"
```

Each step must have a `name` and exactly one of:

- `tool` — call a single tool
- `tools` — call multiple tools in parallel (fan-out)
- `prompt` — an LLM-only step with no tool call

### Step input mappings

The `input` dict maps parameter names to values. Values can be:

- Literal strings: `"Paris"`
- JSONPath-style references to earlier data:
  - `$.input.<field>` — a field from the original agent invocation input
  - `$.steps.<step-name>.output` — the full output of a previous step
  - `$.steps.<step-name>.output.<field>` — a specific field from a previous step's output

### Single tool step

```yaml
- name: compute-sum
  tool: add-numbers
  input:
    a: "$.input.a"
    b: "$.input.b"
```

### Parallel fan-out step

Use `tools` (plural) to call multiple tools concurrently and collect results:

```yaml
- name: research
  tools:
    - tool: search-flights
      input:
        origin: "$.input.origin"
        destination: "$.input.destination"
    - tool: search-hotels
      input:
        destination: "$.input.destination"
```

### LLM-only step

Use `prompt` for a step that has the LLM reason over accumulated data without calling a tool:

```yaml
- name: summarize
  prompt: "Explain the arithmetic result in a clear sentence."
  input:
    first_result: "$.steps.first-add.output"
    final_result: "$.steps.second-add.output"
  system_prompt: "You are a math tutor. Be concise."
```

`system_prompt` is optional and overrides the default built-in message for prompt steps.

## Complete example

```markdown
---
name: math-workflow
description: Multi-step arithmetic workflow with automated pipeline
tools:
  - add-numbers
steps:
  - name: first-add
    tool: add-numbers
    input:
      a: "$.input.a"
      b: "$.input.b"

  - name: second-add
    tool: add-numbers
    input:
      a: "$.steps.first-add.output.result"
      b: "$.input.c"

  - name: summarize
    prompt: "Explain the arithmetic result in a clear sentence."
    input:
      first_result: "$.steps.first-add.output"
      final_result: "$.steps.second-add.output"
---

# Math Workflow

A demonstration workflow that chains two additions and summarizes the result.

Given three numbers (a, b, c), it:
1. Adds a + b
2. Adds the result + c
3. Summarizes the chain with an LLM prompt
```

## Skills without workflow steps

Most skills do not define explicit steps. When `steps:` is omitted, the skill simply makes its tools available to the LLM, which decides when and how to call them based on the skill body instructions and the conversation context.

Use explicit workflow steps when you want deterministic execution order, parallel fan-out, or LLM reasoning steps between tool calls.
