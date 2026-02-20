# Agent Gateway

An opinionated FastAPI extension for building API-first AI agent services. Define agents and skills as markdown files. Get production-ready agent endpoints alongside your own routes — with auth, structured outputs, observability, and outbound notifications.

```bash
pip install agent-gateway
```

```
workspace/
├── agents/
│   └── underwriting/
│       ├── AGENT.md
│       └── BEHAVIOR.md
├── skills/
│   └── credit-assessment/
│       └── SKILL.md
└── tools/
    └── companies-house-check/
        └── TOOL.md
```

```python
from agent_gateway import Gateway

gw = Gateway()  # This IS a FastAPI app

@gw.tool()
async def calculate_risk_score(revenue: float, trading_months: int) -> dict:
    """Calculate a 0-100 risk score from financial indicators."""
    score = 100
    if trading_months < 12: score -= 40
    if revenue < 100_000: score -= 20
    return {"score": max(0, score)}

# Mix agent endpoints with your own FastAPI routes
@gw.get("/api/health")
async def health():
    return {"status": "ok"}

gw.run()
# → POST /v1/agents/underwriting/invoke  (auto-generated from workspace)
# → GET  /api/health                      (your own route)
# → Tools: companies-house-check (file), calculate-risk-score (code)
```

---

## Table of Contents

| | |
|---|---|
| **Concepts** | |
| 1. [What This Is](#1-what-this-is) | 2. [Design Principles](#2-design-principles) |
| 3. [Concepts: Agents, Skills, Tools](#3-concepts-agents-skills-tools) | |
| **Defining Things** | |
| 4. [Developer Experience](#4-developer-experience) | 5. [Workspace Convention](#5-workspace-convention) |
| 6. [Agent Definition](#6-agent-definition) | 7. [Skill Definition](#7-skill-definition) |
| 8. [Tool Definition](#8-tool-definition) | 9. [Configuration](#9-configuration) |
| **Runtime** | |
| 10. [API Layer](#10-api-layer) | 11. [Execution Engine](#11-execution-engine) |
| 12. [Authentication](#12-authentication) | 13. [Outbound Notifications](#13-outbound-notifications) |
| 14. [Structured Output](#14-structured-output) | 15. [Python API](#15-python-api) |
| **Operations** | |
| 16. [CLI](#16-cli) | 17. [Persistence](#17-persistence) |
| 18. [Security](#18-security) | 19. [Observability (OpenTelemetry)](#19-observability-opentelemetry) |
| **Building It** | |
| 20. [Package Structure](#20-package-structure) | 21. [Implementation Plan](#21-implementation-plan) |
| 22. [Technology Choices](#22-technology-choices) | |

---

## 1. What This Is

Agent Gateway is a **FastAPI extension** for building API-first AI agent services. It subclasses `FastAPI` — you get the full power of FastAPI (routes, dependencies, middleware, OpenAPI docs, lifespan) plus an opinionated agent execution layer on top.

You install it, define your agents as markdown files, and get:

- Agent invocation endpoints auto-generated from your workspace
- An execution engine that runs LLM function-calling loops
- API key authentication out of the box
- Outbound notifications to Slack, Teams, and webhooks
- Structured JSON output validated against schemas
- An audit log of every execution and tool call
- OpenTelemetry traces and metrics from day one
- **Everything FastAPI gives you** — add your own routes, use `Depends()`, mount sub-apps, etc.

It is **not** a hosted platform. It is **not** multi-tenant. It runs inside your application, in your infrastructure, under your control.

### Built On FastAPI, Not Beside It

`Gateway` **is** a FastAPI app. It subclasses `FastAPI` directly:

```python
from agent_gateway import Gateway

gw = Gateway()

# This is a FastAPI app — you can add your own routes
@gw.get("/api/health")
async def health():
    return {"status": "ok"}

# Use FastAPI dependencies
from fastapi import Depends

async def get_current_user(authorization: str = Header()):
    return verify_token(authorization)

@gw.get("/api/deals")
async def list_deals(user=Depends(get_current_user)):
    return await fetch_deals(user.id)

gw.run()
# → Your routes + auto-generated agent endpoints, all in one app
```

### What It Replaces

Instead of hand-wiring this every time:

```python
# The old way — bespoke per project
app = FastAPI()
client = anthropic.Client()

@app.post("/api/underwriting/assess")
async def assess(request: Request):
    messages = [{"role": "system", "content": open("prompts/underwriting.txt").read()}]
    messages.append({"role": "user", "content": request.json()["message"]})

    # Hand-rolled function-calling loop
    while True:
        response = client.messages.create(model="...", messages=messages, tools=tools)
        if response.stop_reason != "tool_use":
            break
        for tool_call in response.content:
            if tool_call.type == "tool_use":
                result = execute_tool(tool_call)  # hand-rolled dispatcher
                messages.append(...)

    # Hand-rolled auth, logging, notifications, error handling...
    return {"result": response.content[0].text}
```

You write this:

```python
from agent_gateway import Gateway

gw = Gateway()
gw.run()
```

And define your agents as files. The framework handles everything else.

### Analogies

| Framework | What It Does | Agent Gateway |
|---|---|---|
| **FastAPI** | Turns Python functions into REST APIs | **Extends** FastAPI — adds agent execution to any FastAPI app |
| **Django** | Opinionated web framework with ORM, auth, admin | Opinionated agent framework with execution engine, auth, notifications |
| **Celery** | Turns Python functions into async tasks | Turns agent invocations into async jobs |

---

## 2. Design Principles

### 2.1 Convention Over Configuration

The framework works with zero configuration if you follow the conventions. Put an `AGENT.md` in a folder → it's an agent. Put a `SKILL.md` in a folder → it's a skill. No registration code needed.

### 2.2 Files Are the Source of Truth

Agents and skills are markdown files in a directory. Not database rows. Not YAML configs passed to constructors. Files you can read, diff, review in a PR, and version in git.

### 2.3 API-First, Chat-Second

The primary interface is `POST /v1/agents/{id}/invoke`. Chat apps (Slack, Teams) receive notifications as a side effect. If you want chat-as-input, build that layer on top.

### 2.4 Batteries Included, Ejectable

Auth, notifications, audit logging, and structured output work out of the box. But every component can be swapped, disabled, or extended. Don't need Slack? Don't configure it. Want custom auth? Override the middleware.

### 2.5 Bring Your Own LLM

Works with any LLM provider via LiteLLM. Anthropic, Google, OpenAI, Azure, Bedrock, self-hosted. Configure it once, the framework handles the rest.

### 2.6 The Framework Does the Boring Parts

You write the interesting parts — agent prompts, business logic, skill implementations. The framework handles: HTTP server, request validation, auth, execution loop, tool dispatch, retries, timeouts, audit logging, notifications, cost tracking, structured output parsing.

---

## 3. Concepts: Agents, Skills, Tools

The framework has three core concepts with a clear hierarchy:

```
Agent
├── has skills (high-level workflows)
│   ├── Skill: lead-qualification
│   │   ├── uses tool: companies-house-check
│   │   ├── uses tool: credit-bureau
│   │   └── uses tool: risk-score
│   └── Skill: document-verification
│       ├── uses tool: pdf-extract
│       └── uses tool: companies-house-check
└── has direct tools (low-level capabilities)
    ├── Tool: send-email
    └── Tool: create-crm-note
```

### Tool

A **tool** is a single callable function. It does one thing.

- Has a name, description, and typed parameters
- The LLM can call it during execution
- Defined via `@gw.tool` in Python or `TOOL.md` on the filesystem
- Examples: `companies-house-check`, `calculate-dscr`, `send-slack-message`

### Skill

A **skill** is a higher-level workflow that bundles a prompt with a set of tools. It describes *how* to accomplish a task, not just *what* to call.

- Defined as a `SKILL.md` file with instructions + a list of tools it uses
- The skill's markdown body guides the LLM through a multi-step process
- A skill can reference tools (both `@gw.tool` and `TOOL.md` tools)
- Examples: `lead-qualification`, `credit-assessment`, `portfolio-review`

### Agent

An **agent** is a persona with a system prompt, personality, and a set of skills and tools it can use.

- Defined as a directory with `AGENT.md` + optional `BEHAVIOR.md`
- Has access to skills (which bring their own tools) and direct tools
- Exposed as an API endpoint: `POST /v1/agents/{id}/invoke`
- Examples: `underwriting`, `sales`, `compliance`

### How They Compose

```python
gw = Gateway()

# Define a tool — a single capability
@gw.tool()
async def companies_house_check(company_number: str) -> dict:
    """Query Companies House for company data."""
    ...

@gw.tool()
async def credit_bureau_check(company_id: str) -> dict:
    """Pull credit report for a company."""
    ...

@gw.tool()
async def calculate_risk_score(revenue: float, trading_months: int) -> dict:
    """Calculate a 0-100 risk score."""
    ...

gw.run()
```

Then on the filesystem:

```markdown
# workspace/skills/lead-qualification/SKILL.md
---
name: lead-qualification
description: Qualify an inbound lending lead
tools:
  - companies-house-check
  - credit-bureau-check
  - calculate-risk-score
---

# Lead Qualification

When qualifying a lead, follow these steps:

1. Run a Companies House check to verify the company is active and UK-registered
2. Pull a credit report to check for CCJs, defaults, and adverse indicators
3. Calculate a risk score using the financial data provided
4. Combine all findings into a qualification recommendation

## Criteria
- Minimum 12 months trading
- DSCR above 1.25x
- No active CCJs above £5,000

## Output
Provide: score (0-100), recommendation (QUALIFIED / NEEDS REVIEW / REJECTED),
reasoning, and suggested next action.
```

And the agent references the skill:

```markdown
# workspace/agents/sales/AGENT.md
---
skills:
  - lead-qualification
tools:
  - send-email
  - create-crm-note
---
# Sales Agent

You are a sales assistant. Qualify leads and manage CRM interactions.
```

The sales agent can now:
- Use the `lead-qualification` skill (which brings `companies-house-check`, `credit-bureau-check`, and `calculate-risk-score` tools)
- Use `send-email` and `create-crm-note` tools directly

### The Resolution Chain

When an agent is invoked:

1. Load the agent's skills (from AGENT.md frontmatter `skills` list)
2. For each skill, load its tools (from SKILL.md `tools` list)
3. Load the agent's direct tools (from AGENT.md frontmatter `tools` list)
4. Merge all tools into the LLM's function declarations (deduplicated)
5. Inject skill descriptions into the system prompt so the LLM understands the workflows

The LLM sees all available tools as a flat list. The skill layer is a *prompt-level* concept — it structures how the LLM thinks about using the tools, not a runtime boundary.

---

## 4. Developer Experience

### 3.1 Getting Started

```bash
pip install agent-gateway
agent-gateway init my-project
cd my-project
```

This scaffolds:

```
my-project/
├── workspace/
│   ├── agents/
│   │   └── assistant/
│   │       ├── AGENT.md
│   │       └── BEHAVIOR.md
│   ├── skills/
│   │   └── hello/
│   │       └── SKILL.md
│   └── gateway.yaml
├── app.py
├── .env
└── requirements.txt
```

`app.py`:
```python
from agent_gateway import Gateway

gw = Gateway()
gw.run()
```

```bash
python app.py
# → Agent Gateway running on http://localhost:8000
# → Agents: assistant
# → Skills: hello
# → Docs:   http://localhost:8000/docs
```

Test it:
```bash
curl -X POST http://localhost:8000/v1/agents/assistant/invoke \
  -H "Authorization: Bearer dev-key" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, what can you do?"}'
```

### 3.2 Adding an Agent

```bash
mkdir workspace/agents/underwriting
```

Write `workspace/agents/underwriting/AGENT.md`:
```markdown
# Underwriting Agent

You assist the credit team by verifying documents, analysing financials,
and providing decision-support recommendations.

## Core Rules

- All credit decisions require human approval
- Flag adverse indicators: CCJs, winding-up petitions, late filings
- Apply credit policy: min 12 months trading, DSCR > 1.25x

## Available Skills

Use the `companies-house-check` skill when you need company data.
```

Write `workspace/agents/underwriting/BEHAVIOR.md`:
```markdown
# BEHAVIOR

Thorough, analytical, and risk-aware.

- Accuracy matters more than speed
- Flag risks clearly — don't soften adverse findings
- British English spelling
```

The gateway hot-reloads. The agent is live at `POST /v1/agents/underwriting/invoke`. No code changes. No restart.

### 4.3 Adding a Tool (File-Based)

```bash
mkdir workspace/tools/companies-house-check
```

Write `workspace/tools/companies-house-check/TOOL.md`:
```markdown
---
name: companies-house-check
description: Query Companies House for company data
type: http
http:
  method: GET
  url: "${LENKIE_API_URL}/api/companies-house/${company_number}"
  headers:
    Authorization: "Bearer ${LENKIE_API_TOKEN}"
parameters:
  company_number:
    type: string
    description: "8-digit UK Companies House number"
    required: true
---

# Companies House Check

Retrieves company profile, officers, filing history, and charges.
```

Hot-reloads. The tool is now available to all agents.

### 4.4 Adding a Tool (Code)

In your `app.py`:

```python
from agent_gateway import Gateway

gw = Gateway()

@gw.tool()
async def calculate_risk_score(
    revenue: float,
    trading_months: int,
    ccj_count: int = 0,
) -> dict:
    """Calculate a 0-100 risk score from financial indicators."""
    score = 100
    if trading_months < 12:
        score -= 40
    if ccj_count > 0:
        score -= 30 * ccj_count
    if revenue < 100_000:
        score -= 20
    return {"score": max(0, score), "risk_level": "low" if score >= 70 else "high"}

gw.run()
```

Parameters, types, and descriptions are inferred from the function signature. No manual schema needed.

### 4.5 Adding a Skill

A skill bundles tools into a workflow. Create `workspace/skills/lead-qualification/SKILL.md`:

```markdown
---
name: lead-qualification
description: Qualify an inbound lending lead end-to-end
tools:
  - companies-house-check
  - calculate-risk-score
---

# Lead Qualification

1. Use `companies-house-check` to verify the company is active and UK-registered
2. Use `calculate-risk-score` with the financial data provided
3. Combine findings into a QUALIFIED / NEEDS REVIEW / REJECTED recommendation
```

Then reference the skill in the agent's AGENT.md frontmatter:

```yaml
---
skills:
  - lead-qualification
---
```

The agent now has the lead qualification workflow and both tools available.

---

## 5. Workspace Convention

### 5.1 Directory Layout

```
workspace/
├── gateway.yaml                       # Gateway configuration
│
├── agents/                            # Agent definitions
│   ├── AGENTS.md                      # Root system prompt (shared by all agents)
│   ├── BEHAVIOR.md                    # Root behavior/guardrails (shared by all agents)
│   │
│   ├── underwriting/                  # Agent: underwriting
│   │   ├── AGENT.md                   # Agent prompt + frontmatter config (required)
│   │   └── BEHAVIOR.md               # Agent-specific behavior/guardrails (optional)
│   │
│   ├── sales/                         # Agent: sales
│   │   ├── AGENT.md
│   │   └── BEHAVIOR.md
│   │
│   └── compliance/                    # Agent: compliance
│       └── AGENT.md                   # Minimal — just AGENT.md is enough
│
├── skills/                            # Skills (workflows that use tools)
│   ├── lead-qualification/
│   │   └── SKILL.md                   # Guides the LLM through a multi-step qualification
│   ├── credit-assessment/
│   │   └── SKILL.md                   # Full credit assessment workflow
│   └── portfolio-review/
│       └── SKILL.md                   # Portfolio monitoring workflow
│
└── tools/                             # Tools (single capabilities)
    ├── companies-house-check/
    │   └── TOOL.md                    # HTTP tool — calls external API
    ├── risk-score/
    │   ├── TOOL.md                    # Function tool
    │   └── handler.py                 # Python handler
    └── pdf-extract/
        ├── TOOL.md                    # Script tool
        └── run.py                     # Standalone script
```

### 5.2 Discovery Rules

On startup, the gateway scans the workspace:

1. **Agents**: Every subdirectory of `workspace/agents/` containing an `AGENT.md` is an agent. Directory name = agent ID.
2. **Skills**: Every subdirectory of `workspace/skills/` containing a `SKILL.md` is a skill. Directory name = skill ID.
3. **Tools**: Every subdirectory of `workspace/tools/` containing a `TOOL.md` is a tool. Directory name = tool ID.
4. **Root prompts**: `workspace/agents/AGENTS.md` and `workspace/agents/BEHAVIOR.md` are prepended to every agent's system prompt.
5. **Code tools**: Tools registered via `@gw.tool` are merged into the registry alongside file-based tools.

### 5.3 Hot-Reload

The gateway watches the workspace directory for changes. When a file is created, modified, or deleted:

- New agent directory with AGENT.md → agent registered, endpoint available
- Modified AGENT.md/BEHAVIOR.md → agent prompt updated (next invocation uses new prompt)
- Deleted AGENT.md → agent deregistered, endpoint returns 404
- Same for skills and tools

No restart needed during development. In production, use `POST /v1/reload` or restart the process.

### 5.4 Customising the Workspace Path

```python
gw = Gateway(workspace="./my-agents")
```

Or via environment variable:

```bash
AGENT_GATEWAY_WORKSPACE=./my-agents python app.py
```

---

## 6. Agent Definition

### 6.1 AGENT.md — The System Prompt

The only required file. Pure markdown. Becomes the agent's system prompt.

```markdown
# Underwriting Agent

You assist the credit team by verifying documents, analysing financials,
running Companies House checks, assessing risk, and providing
decision-support recommendations.

## Core Rules

- All credit decisions require human approval — provide recommendations only
- Cross-reference bank statement data with management accounts
- Flag adverse indicators: CCJs, winding-up petitions, late filings
- Apply credit policy: min 12 months trading, DSCR > 1.25x, no CCJs > £5k

## Workflow

1. Start with a Companies House check
2. Review company status, filing history, directors
3. Flag adverse indicators
4. Provide a structured recommendation

## Available Skills

- `companies-house-check` — company verification
- `risk-score` — calculate risk from financials
- `credit-bureau` — pull credit report
```

No special syntax. No frontmatter required. Just write what you want the agent to do.

### 6.2 BEHAVIOR.md — Guardrails & Behavior

Optional. Controls tone, boundaries, and behaviour. Injected after AGENT.md in the system prompt.

```markdown
# BEHAVIOR

Thorough, analytical, and risk-aware.

## Tone

- Professional and precise
- Direct about risks — don't soften adverse findings
- British English spelling

## Boundaries

- Never approve or reject credit applications
- Never share credentials
- Ask for clarification when data is ambiguous
```

### 6.3 AGENT.md Frontmatter — Agent Settings

AGENT.md supports optional YAML frontmatter for machine-readable config.

**Each agent can use a different LLM.** This is configured in AGENT.md frontmatter via the `model` block. If omitted, the agent inherits the default from `gateway.yaml`.

```markdown
---
# LLM — each agent picks its own model
model:
  name: google/gemini-2.5-flash           # LiteLLM model identifier
  temperature: 0.1
  max_tokens: 4096
  fallback: anthropic/claude-sonnet-4-5-20250929

# Skills — high-level workflows (each brings its own tools)
skills:
  - credit-assessment
  - document-verification

# Tools — direct capabilities (available alongside skill tools)
tools:
  - companies-house-check
  - send-email
  - create-crm-note

guardrails:
  max_tool_calls: 20
  max_iterations: 10
  timeout_ms: 60000

output_schema:
  type: object
  properties:
    recommendation:
      type: string
      enum: [APPROVE, REFER, DECLINE]
    score:
      type: integer
      minimum: 0
      maximum: 100
    reasoning:
      type: array
      items:
        type: string

notifications:
  on_complete:
    - channel: slack
      target: "#underwriting-alerts"
  on_error:
    - channel: slack
      target: "#engineering-alerts"
---

# Underwriting Agent

You assist the credit team by verifying documents, analysing financials,
and providing decision-support recommendations.
```

#### Why Per-Agent Models?

Different agents have different needs:

| Agent | Best Model | Why |
|---|---|---|
| **Triage / Router** | `gemini-2.5-flash`, `claude-haiku-4-5` | Fast, cheap — just classifies intent |
| **Underwriting** | `claude-sonnet-4-5`, `gpt-4o` | Needs strong reasoning for risk assessment |
| **Data Extraction** | `gemini-2.5-flash` | High throughput, structured output |
| **Compliance Review** | `claude-opus-4-6` | Highest accuracy for regulatory work |

#### Model Resolution Order

```
Agent AGENT.md frontmatter → gateway.yaml default → framework default (gpt-4o-mini)
```

Specifically:

```
1. agent's AGENT.md model.name          → used if present
2. gateway.yaml model.default           → fallback for agents without model config
3. framework built-in default           → gpt-4o-mini (works out of the box)
```

Temperature, max_tokens, and fallback follow the same cascade.

#### Example: Three Agents, Three Models

```
workspace/agents/
├── triage/
│   └── AGENT.md           # model.name: google/gemini-2.5-flash
├── underwriting/
│   ├── AGENT.md           # model.name: anthropic/claude-sonnet-4-5-20250929
│   └── BEHAVIOR.md
└── compliance/
    └── AGENT.md           # model.name: anthropic/claude-opus-4-6
```

```yaml
# gateway.yaml sets the default — agents without a model block get this
model:
  default: "google/gemini-2.5-flash"

# But each agent overrides it in their AGENT.md frontmatter:
# triage/AGENT.md → gemini flash (fast, cheap routing)
# underwriting/AGENT.md → claude sonnet (strong reasoning)
# compliance/AGENT.md → claude opus (maximum accuracy)
```

All model identifiers use the **LiteLLM format** (`provider/model`), so any provider supported by LiteLLM works: OpenAI, Anthropic, Google, Azure, Bedrock, Ollama, etc.

**If no model block is present in AGENT.md**, the agent inherits defaults from `gateway.yaml`.

### 6.4 Prompt Assembly

When an agent is invoked, the framework assembles the system prompt by concatenating:

```
1. workspace/agents/AGENTS.md           (root context, if exists)
2. workspace/agents/BEHAVIOR.md         (root behavior/guardrails, if exists)
3. workspace/agents/{agent}/AGENT.md    (agent system prompt)
4. workspace/agents/{agent}/BEHAVIOR.md (agent behavior/guardrails, if exists)
5. [auto-injected skill descriptions]   (from SKILL.md for each skill in AGENT.md frontmatter)
6. [auto-injected tool descriptions]    (from TOOL.md / @gw.tool for direct tools)
7. [auto-injected config context]       (from gateway.yaml business config, if any)
```

Skills are injected as workflow instructions. Tools are registered as LLM function declarations. The LLM sees both — the skill text guides *how* to use the tools, and the tool declarations define *what* it can call.

### 6.5 Minimum Viable Agent

A single file is enough:

```
workspace/agents/my-agent/AGENT.md
```

```markdown
# My Agent

You are a helpful assistant. Answer questions clearly and concisely.
```

That's a working agent. Everything else is optional.

---

## 7. Skill Definition

A skill is a **workflow** — a set of instructions that guide the LLM through a multi-step process, with a declared list of tools it can use.

Skills live in `workspace/skills/`. Each skill is a directory with a `SKILL.md` file.

### 7.1 SKILL.md Format

```markdown
---
name: lead-qualification
description: Qualify an inbound SME lending lead end-to-end
tools:
  - companies-house-check
  - credit-bureau-check
  - calculate-risk-score
---

# Lead Qualification

When asked to qualify a lead, follow these steps:

## Step 1: Company Verification

Use `companies-house-check` to verify:
- Company is active and UK-registered
- Trading for at least 12 months
- No winding-up petitions or dissolved status

## Step 2: Credit Check

Use `credit-bureau-check` to review:
- Active CCJs (reject if any above £5,000)
- Payment defaults in last 12 months
- Overall credit score

## Step 3: Risk Scoring

Use `calculate-risk-score` with the financial data gathered. Factor in:
- Revenue vs requested facility size
- DSCR (must be above 1.25x)
- Sector risk

## Step 4: Recommendation

Combine all findings into a clear recommendation:
- **QUALIFIED** — meets all criteria, proceed to offer
- **NEEDS REVIEW** — marginal on one or more criteria, flag for human review
- **REJECTED** — fails hard criteria (CCJs, trading history, dissolved)

Always provide: score (0-100), recommendation, bullet-point reasoning, and
suggested next action for the sales team.
```

The `tools:` list in frontmatter declares which tools this skill needs. When an agent uses this skill, those tools are automatically made available to the LLM.

### 7.2 Skills vs Tools

| | Skill | Tool |
|---|---|---|
| **What** | A workflow with instructions | A single callable function |
| **Defined by** | SKILL.md (markdown instructions + tool list) | TOOL.md or `@gw.tool` (parameters + handler) |
| **The LLM sees** | Prompt text injected into system message | Function declaration it can call |
| **Contains** | References to tools | Implementation (HTTP call, Python function, script) |
| **Example** | "Lead Qualification" — a 4-step process | "Companies House Check" — one API call |

A skill is pure prompt engineering. It doesn't execute anything itself — it tells the LLM *how* to use tools to accomplish a task.

### 7.3 SKILL.md Frontmatter Reference

| Field | Required | Default | Description |
|---|---|---|---|
| `name` | yes | — | Skill identifier |
| `description` | yes | — | One-line description |
| `tools` | no | `[]` | Tools this skill uses (by name) |
| `version` | no | `1.0.0` | Skill version |

The markdown body is the skill's instructions — injected into the system prompt when this skill is active.

### 7.4 Skill Without Tools

A skill can have no tools. It's just structured instructions for the LLM:

```markdown
---
name: email-drafting
description: Draft professional emails following company tone guidelines
---

# Email Drafting

When asked to draft an email, follow these guidelines:
- Professional but warm tone
- Keep paragraphs short (2-3 sentences)
- Always include a clear call to action
- British English spelling
```

---

## 8. Tool Definition

A tool is a **single capability** the LLM can call. There are two ways to define tools — both are first-class.

### 8.1 File-Based Tools (TOOL.md)

Tools live in `workspace/tools/`. Each tool is a directory with a `TOOL.md` file.

#### HTTP Tool

Calls an external API. No Python code needed.

```markdown
---
name: companies-house-check
description: Query Companies House for company data
type: http
http:
  method: GET
  url: "${COMPANIES_HOUSE_API_URL}/company/${company_number}"
  headers:
    Authorization: "Bearer ${COMPANIES_HOUSE_API_KEY}"
  timeout_ms: 10000
parameters:
  company_number:
    type: string
    description: "8-digit UK Companies House number"
    required: true
---

# Companies House Check

Retrieves company profile, officers, filing history, and charges.
```

Environment variables in `${}` are resolved at runtime from the process environment or `.env` file. They are never exposed to the LLM.

#### Function Tool

Calls a Python function in `handler.py`.

```markdown
---
name: risk-score
description: Calculate risk score from financial indicators
type: function
parameters:
  revenue:
    type: number
    required: true
  trading_months:
    type: integer
    required: true
---

# Risk Score

Calculates a 0-100 risk score based on financial indicators.
```

`handler.py` in the same directory:

```python
async def handle(params, context):
    score = 100
    if params["trading_months"] < 12:
        score -= 40
    if params["revenue"] < 100_000:
        score -= 20
    return {"score": max(0, score)}
```

#### Script Tool

Runs a standalone script. Input via stdin (JSON), output via stdout (JSON).

```markdown
---
name: pdf-extract
description: Extract financial data from PDF documents
type: script
script:
  command: "python run.py"
  timeout_ms: 30000
parameters:
  document_url:
    type: string
    required: true
---
```

### 8.2 Code-Based Tools (`@gw.tool`)

See [Section 15.5](#155-code-defined-tools-gwtool) for the full decorator API with type hints, Pydantic models, and examples.

```python
@gw.tool()
async def companies_house_check(company_number: str) -> dict:
    """Query Companies House for company data."""
    ...

@gw.tool(allowed_agents=["underwriting"])
async def submit_credit_decision(company_id: str, decision: str) -> dict:
    """Submit a credit decision. Restricted to underwriting."""
    ...
```

Code tools and file tools are merged into a single registry. If both exist with the same name, the code tool wins.

### 8.3 Tool Permissions (Optional)

In TOOL.md frontmatter or `@gw.tool` decorator:

```yaml
permissions:
  allowed_agents: [underwriting]
  require_approval: true
```

- `allowed_agents` — only these agents can use this tool
- `require_approval` — pauses execution and fires an approval notification before running

### 8.4 TOOL.md Frontmatter Reference

| Field | Required | Default | Description |
|---|---|---|---|
| `name` | yes | — | Tool identifier |
| `description` | yes | — | One-line description (shown to LLM) |
| `type` | no | `function` | `http`, `function`, `script` |
| `parameters` | no | `{}` | Parameters for LLM function calling |
| `parameters.{name}.type` | yes (if param) | — | `string`, `number`, `integer`, `boolean`, `array`, `object` |
| `parameters.{name}.description` | yes (if param) | — | Description for the LLM |
| `parameters.{name}.required` | no | `false` | Whether the parameter is required |
| `parameters.{name}.enum` | no | — | Allowed values |
| `http` | if type=http | — | HTTP configuration |
| `http.method` | yes | — | `GET`, `POST`, `PUT`, `DELETE` |
| `http.url` | yes | — | URL template with `${var}` substitution |
| `http.headers` | no | `{}` | Request headers |
| `http.body` | no | — | Request body template (for POST/PUT) |
| `http.timeout_ms` | no | `15000` | Request timeout |
| `script.command` | if type=script | — | Shell command to run |
| `script.timeout_ms` | no | `30000` | Script timeout |
| `permissions.allowed_agents` | no | all | Which agents can use this tool |
| `permissions.require_approval` | no | `false` | Require human approval before execution |
| `version` | no | `1.0.0` | Tool version |

---

## 9. Configuration

### 7.1 gateway.yaml

Central configuration file. Everything has sensible defaults — this file is optional for getting started.

```yaml
# workspace/gateway.yaml

# Server
server:
  host: "0.0.0.0"
  port: 8000
  workers: 1                           # Uvicorn workers

# Default model for agents that don't specify one in AGENT.md frontmatter
# Uses LiteLLM format: provider/model
model:
  default: "google/gemini-2.5-flash"
  temperature: 0.1
  max_tokens: 4096
  fallback: "anthropic/claude-sonnet-4-5-20250929"

# Default guardrails
guardrails:
  max_tool_calls: 20
  max_iterations: 10
  timeout_ms: 60000

# Authentication
auth:
  enabled: true
  mode: api_key                        # api_key | bearer_jwt | custom | none
  api_keys:
    - name: "dev-key"
      key: "${AGENT_GATEWAY_DEV_KEY}"  # From .env
      scopes: ["*"]

# Notifications
notifications:
  slack:
    enabled: false
    bot_token: "${SLACK_BOT_TOKEN}"
  teams:
    enabled: false
    webhook_url: "${TEAMS_WEBHOOK_URL}"
  webhooks: []

# Persistence (for execution history + audit log)
persistence:
  enabled: true
  backend: sqlite                      # sqlite | postgresql
  url: "sqlite:///agent_gateway.db"    # Default: SQLite in project root
  # url: "postgresql://user:pass@localhost:5432/agent_gateway"

# Business context (injected into agent prompts as additional context)
context:
  company: "Lenkie"
  product: "Grow Now, Pay Later credit facilities for UK SMEs"
  credit_thresholds:
    min_trading_months: 12
    min_dscr: 1.25
    max_ccj_amount_gbp: 5000
```

### 7.2 Environment Variables

All settings can be overridden via environment variables prefixed with `AGENT_GATEWAY_`:

```bash
AGENT_GATEWAY_PORT=9000
AGENT_GATEWAY_MODEL_DEFAULT=anthropic/claude-sonnet-4-5-20250929
AGENT_GATEWAY_AUTH_ENABLED=false
```

### 7.3 .env File

The framework loads `.env` from the workspace root (or project root). Used for secrets.

```bash
# .env
GEMINI_API_KEY=AIzaSy...
ANTHROPIC_API_KEY=sk-ant-...
SLACK_BOT_TOKEN=xoxb-...
COMPANIES_HOUSE_API_KEY=...
LENKIE_API_URL=http://localhost:8080
LENKIE_API_TOKEN=...
AGENT_GATEWAY_DEV_KEY=my-secret-dev-key
```

### 7.4 Configuration Precedence

```
Environment variables > gateway.yaml > defaults
```

For agent-specific settings:
```
AGENT.md frontmatter > gateway.yaml > framework defaults
```

---

## 10. API Layer

### 8.1 Auto-Generated Endpoints

The framework generates these endpoints from the workspace:

#### Agent Invocation

```
POST /v1/agents/{agent_id}/invoke
```

Request:
```json
{
  "message": "Assess Acme Corp for a £50k facility",
  "context": {
    "user_id": "usr_123",
    "metadata": {"deal_id": "deal_456"}
  },
  "options": {
    "async": false,
    "timeout_ms": 30000,
    "callback_url": "https://myapp.com/webhooks/result",
    "notify": ["slack:#underwriting-alerts"],
    "stream": false
  }
}
```

Response (sync):
```json
{
  "execution_id": "exec_abc123",
  "agent_id": "underwriting",
  "status": "completed",
  "result": {
    "output": {
      "recommendation": "APPROVE",
      "score": 85,
      "reasoning": ["3+ years trading", "Strong revenue"]
    },
    "raw_text": "Acme Corp qualifies..."
  },
  "usage": {
    "model": "google/gemini-2.5-flash",
    "input_tokens": 1240,
    "output_tokens": 380,
    "cost_usd": 0.0012,
    "tool_calls": 2,
    "duration_ms": 4520
  }
}
```

Response (async):
```json
{
  "execution_id": "exec_abc123",
  "status": "queued",
  "poll_url": "/v1/executions/exec_abc123"
}
```

#### Streaming

```
POST /v1/agents/{agent_id}/invoke
Accept: text/event-stream
```

```
event: token
data: {"text": "Acme Corp "}

event: tool_call
data: {"tool": "companies-house-check", "args": {"company_number": "12345678"}}

event: tool_result
data: {"tool": "companies-house-check", "duration_ms": 340}

event: done
data: {"execution_id": "exec_abc123", "usage": {...}}
```

#### Execution History

```
GET  /v1/executions/{execution_id}        # Get execution result
GET  /v1/executions?agent_id=underwriting  # List executions
POST /v1/executions/{execution_id}/cancel  # Cancel running execution
```

#### Introspection

```
GET  /v1/agents                            # List discovered agents
GET  /v1/agents/{agent_id}                 # Agent details (parsed from markdown)
GET  /v1/skills                            # List discovered skills
GET  /v1/skills/{skill_id}                 # Skill details (tools it uses)
GET  /v1/tools                             # List all tools (file + code)
GET  /v1/tools/{tool_id}                   # Tool details
POST /v1/reload                            # Re-scan workspace
GET  /v1/health                            # Health check
```

#### Webhook Receiver

```
POST /v1/hooks/{hook_id}                   # Inbound webhook → triggers agent
```

### 8.2 OpenAPI Docs

Auto-generated at `/docs` (Swagger UI) and `/v1/openapi.json`. Agent-specific parameters and output schemas are included when defined in AGENT.md frontmatter.

### 8.3 Batch Invocation

```
POST /v1/agents/{agent_id}/batch
```

```json
{
  "items": [
    {"message": "Assess Acme Corp..."},
    {"message": "Assess Beta Inc..."},
    {"message": "Assess Gamma Ltd..."}
  ],
  "options": {
    "concurrency": 5,
    "callback_url": "https://myapp.com/webhooks/batch-done"
  }
}
```

---

## 11. Execution Engine

### 9.1 The Loop

When `POST /v1/agents/{id}/invoke` is called:

```
1. Load agent (AGENT.md + optional BEHAVIOR.md from filesystem)
2. Resolve model (agent AGENT.md frontmatter → gateway.yaml → framework default)
3. Resolve agent's skills → collect tools from each skill
4. Resolve agent's direct tools
5. Assemble system prompt (layered markdown + skill instructions)
6. Build LLM tool declarations from all resolved tools (deduplicated)
7. Create execution record in database

8. LLM function-calling loop (using agent's resolved model):
   ┌──────────────────────────────────────────────────┐
   │  Send messages + tools to LLM                    │
   │      ↓                                           │
   │  LLM responds with text or tool_calls            │
   │      ↓                                           │
   │  If tool_calls:                                  │
   │    For each tool_call:                           │
   │      - Validate args against tool schema         │
   │      - Check permissions (allowed_agents)        │
   │      - Check approval gate (require_approval)    │
   │      - Execute tool (HTTP / function / script)   │
   │      - Log to audit trail                        │
   │      - Append result to messages                 │
   │    Loop back to top                              │
   │                                                  │
   │  If text (no tool_calls):                        │
   │    Break — we have our answer                    │
   └──────────────────────────────────────────────────┘

6. Parse structured output (if output_schema defined in AGENT.md frontmatter)
7. Save execution result
8. Fire notifications (Slack, Teams, webhooks)
9. Return response
```

### 9.2 Guardrails

Configured in AGENT.md frontmatter or gateway.yaml:

| Guardrail | Default | Description |
|---|---|---|
| `max_tool_calls` | 20 | Max total tool calls per execution |
| `max_iterations` | 10 | Max LLM round-trips |
| `timeout_ms` | 60000 | Total execution timeout |
| `require_approval` | `[]` | Skills requiring human approval |

When a limit is hit, the execution returns a partial result with a `guardrail_triggered` flag.

### 9.3 Approval Gates

When a skill has `require_approval: true`:

1. Execution pauses
2. Notification sent (Slack button, webhook, etc.)
3. Execution status → `approval_pending`
4. Human approves/denies via Slack button or `POST /v1/executions/{id}/approve`
5. Execution resumes or terminates

### 9.4 Model Resolution & Failover

Each agent resolves its model at invocation time:

```
Agent AGENT.md model.name  →  gateway.yaml model.default  →  gpt-4o-mini
```

**Failover**: If the primary model returns an error (rate limit, timeout, 5xx), the framework automatically retries with the fallback model. The fallback follows the same cascade:

```
Agent AGENT.md model.fallback  →  gateway.yaml model.fallback  →  none
```

```yaml
# Agent-level (agents/underwriting/AGENT.md frontmatter)
---
model:
  name: anthropic/claude-sonnet-4-5-20250929
  fallback: google/gemini-2.5-flash
---

# Gateway-level default (gateway.yaml)
model:
  default: "google/gemini-2.5-flash"
  fallback: "anthropic/claude-sonnet-4-5-20250929"
```

All failover events are logged in the execution trace so you can see when and why a model switch happened.

### 9.5 Async Execution

When `"async": true`:

1. API returns immediately with `execution_id` and `202 Accepted`
2. Execution runs in a background worker (asyncio task or separate worker process)
3. Client polls `GET /v1/executions/{id}` or receives result via `callback_url`

For production deployments with high throughput, use a Redis-backed job queue:

```yaml
# gateway.yaml
queue:
  backend: redis                       # memory | redis
  url: "redis://localhost:6379"
```

---

## 12. Authentication

### 10.1 API Key Auth (Default)

Out of the box, the gateway uses API key authentication:

```yaml
# gateway.yaml
auth:
  mode: api_key
  api_keys:
    - name: "production"
      key: "${API_KEY_PRODUCTION}"
      scopes: ["agents:invoke", "executions:read"]
    - name: "admin"
      key: "${API_KEY_ADMIN}"
      scopes: ["*"]
```

```bash
curl -H "Authorization: Bearer $API_KEY_PRODUCTION" \
  http://localhost:8000/v1/agents/underwriting/invoke
```

### 10.2 Scopes

| Scope | Allows |
|---|---|
| `agents:invoke` | Invoke any agent |
| `agents:invoke:{agent_id}` | Invoke a specific agent only |
| `executions:read` | Read execution history |
| `executions:cancel` | Cancel running executions |
| `admin` | Full access (reload, health, etc.) |
| `*` | Everything |

### 10.3 Custom Auth

Override the auth middleware for JWT, OAuth2, or anything else:

```python
from agent_gateway import Gateway
from agent_gateway.auth import AuthResult

async def my_auth(request) -> AuthResult:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    user = await verify_jwt(token)  # Your logic
    return AuthResult(
        authenticated=True,
        identity=user.email,
        scopes=user.permissions,
    )

gw = Gateway(auth=my_auth)
gw.run()
```

### 10.4 Disabling Auth

For development or internal services behind a VPN:

```yaml
auth:
  mode: none
```

Or:
```python
gw = Gateway(auth=False)
```

### 10.5 Outbound Webhook Signatures

All outbound webhooks (callback URLs, notification webhooks) include HMAC signatures:

```
X-AgentGateway-Signature: sha256=abc123...
X-AgentGateway-Timestamp: 1708000000
```

Configure the signing secret:
```yaml
notifications:
  webhook_secret: "${WEBHOOK_SECRET}"
```

---

## 13. Outbound Notifications

### 11.1 Channels

#### Slack

```yaml
notifications:
  slack:
    enabled: true
    bot_token: "${SLACK_BOT_TOKEN}"
```

Agent AGENT.md frontmatter:
```yaml
notifications:
  on_complete:
    - channel: slack
      target: "#underwriting-alerts"
  on_error:
    - channel: slack
      target: "#engineering-alerts"
```

Messages are formatted with rich blocks — agent name, result summary, execution link.

#### Microsoft Teams

```yaml
notifications:
  teams:
    enabled: true
    webhook_url: "${TEAMS_WEBHOOK_URL}"
```

Sends Adaptive Cards with structured results.

#### Generic Webhook

```yaml
notifications:
  webhooks:
    - name: "crm-integration"
      url: "https://api.example.com/webhooks/agent-events"
      secret: "${WEBHOOK_SECRET_CRM}"
      events: ["execution.completed", "execution.failed"]
```

### 11.2 Notification Events

| Event | When |
|---|---|
| `execution.completed` | Agent finishes successfully |
| `execution.failed` | Agent encounters an error |
| `execution.timeout` | Agent exceeds timeout |
| `approval.required` | A skill needs human approval |
| `approval.granted` | Human approves |
| `approval.denied` | Human denies |

### 11.3 Per-Agent Notifications

In the agent's AGENT.md frontmatter:

```yaml
notifications:
  on_complete:
    - channel: slack
      target: "#underwriting-alerts"
    - channel: webhook
      target: "crm-integration"
  on_error:
    - channel: slack
      target: "#engineering-alerts"
  on_approval_required:
    - channel: slack
      target: "#approvals"
```

### 11.4 Programmatic Notifications

```python
from agent_gateway import Gateway

gw = Gateway()

@gw.on("execution.completed")
async def notify_crm(execution):
    await crm_client.update_deal(
        deal_id=execution.context.get("deal_id"),
        status="assessed",
        score=execution.result.output.get("score"),
    )
```

---

## 14. Structured Output

### 12.1 Output Schema

Define in the agent's AGENT.md frontmatter:

```yaml
output_schema:
  type: object
  properties:
    recommendation:
      type: string
      enum: [APPROVE, REFER, DECLINE]
    score:
      type: integer
      minimum: 0
      maximum: 100
    reasoning:
      type: array
      items:
        type: string
  required: [recommendation, score, reasoning]
```

### 12.2 How It Works

1. If the LLM supports native structured output (OpenAI `response_format`, Gemini `response_schema`), the framework uses it directly
2. Otherwise, the schema is appended to the system prompt with instructions to return JSON
3. The response is parsed and validated against the schema
4. If validation fails, the framework retries once with a correction prompt
5. The validated output is returned as `result.output` (structured) alongside `result.raw_text` (original)

### 12.3 No Schema? No Problem

If no `output_schema` is defined, the agent returns free-text in `result.raw_text`. The `result.output` field is `null`.

---

## 15. Python API

### 15.1 Gateway Is a FastAPI App

`Gateway` subclasses `FastAPI`. Everything you can do with a FastAPI app, you can do with a Gateway.

```python
from agent_gateway import Gateway

# Gateway(**kwargs) passes unknown kwargs to FastAPI(...)
gw = Gateway(
    workspace="./workspace",           # Agent Gateway config
    auth=True,                         # Agent Gateway config
    reload=True,                       # Hot-reload workspace
    # --- Everything below is standard FastAPI ---
    title="Lenkie Agent API",
    version="1.0.0",
    docs_url="/docs",
)

gw.run(host="0.0.0.0", port=8000)
```

Because `Gateway` IS FastAPI, you get:

- **OpenAPI docs** at `/docs` and `/redoc` — including auto-generated agent endpoints
- **Dependency injection** via `Depends()`
- **Background tasks**, **WebSockets**, **file uploads** — anything FastAPI supports
- **Middleware** via `@gw.middleware` or `gw.add_middleware()`
- **Lifespan** events via FastAPI's `lifespan` parameter
- **TestClient** for testing — `from fastapi.testclient import TestClient; client = TestClient(gw)`

### 15.2 Add Your Own Routes

Agent endpoints are auto-generated from the workspace. Your own routes live alongside them:

```python
from agent_gateway import Gateway
from fastapi import Depends, Header, HTTPException

gw = Gateway()

# --- Your custom routes ---

async def verify_api_key(x_api_key: str = Header()):
    if x_api_key != "secret":
        raise HTTPException(status_code=401)
    return x_api_key

@gw.get("/api/deals")
async def list_deals(key=Depends(verify_api_key)):
    return [{"id": "deal_1", "status": "active"}]

@gw.post("/api/webhooks/stripe")
async def stripe_webhook(payload: dict):
    # Handle Stripe events, then maybe invoke an agent
    result = await gw.invoke("billing", message=f"Process event: {payload['type']}")
    return {"status": "processed"}

gw.run()
# Auto-generated:  POST /v1/agents/{id}/invoke, GET /v1/agents, etc.
# Your routes:     GET /api/deals, POST /api/webhooks/stripe
# All in one app, one process, one OpenAPI spec
```

### 15.3 Programmatic Invocation

Use agents from Python code without going through the HTTP API:

```python
from agent_gateway import Gateway

gw = Gateway()

# Invoke an agent directly
result = await gw.invoke(
    agent_id="underwriting",
    message="Assess Acme Corp for a £50k facility",
    context={"deal_id": "deal_456"},
)

print(result.output)          # Structured output
print(result.raw_text)        # Raw LLM text
print(result.usage.cost_usd)  # Cost
```

### 15.4 Event Hooks

```python
gw = Gateway()

@gw.on("execution.started")
async def on_start(execution):
    print(f"Agent {execution.agent_id} started")

@gw.on("execution.completed")
async def on_complete(execution):
    print(f"Agent {execution.agent_id} completed: {execution.result.output}")

@gw.on("tool.called")
async def on_tool(event):
    print(f"Tool {event.tool_id} called with {event.args}")
```

### 15.5 Code-Defined Tools (`@gw.tool`)

Register tools directly in Python. This is a first-class way to give agents capabilities.

LLMs require tools in a specific format — a JSON Schema describing the function name, description, and each parameter's type, description, and constraints. The `@gw.tool` decorator builds this spec from your Python code. There are multiple ways to specify inputs, from minimal to fully explicit.

#### Way 1: Annotated Types (Recommended)

Use `Annotated` to attach descriptions to parameters. This is the cleanest way to give the LLM good parameter descriptions.

```python
from typing import Annotated
from agent_gateway import Gateway

gw = Gateway()

@gw.tool()
async def companies_house_check(
    company_number: Annotated[str, "8-digit UK Companies House number"],
) -> dict:
    """Query Companies House API for company verification and officer data."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{os.environ['LENKIE_API_URL']}/api/companies-house/{company_number}",
            headers={"Authorization": f"Bearer {os.environ['LENKIE_API_TOKEN']}"},
        )
        resp.raise_for_status()
        return resp.json()
```

This generates the following tool spec for the LLM:

```json
{
  "type": "function",
  "function": {
    "name": "companies_house_check",
    "description": "Query Companies House API for company verification and officer data.",
    "parameters": {
      "type": "object",
      "properties": {
        "company_number": {
          "type": "string",
          "description": "8-digit UK Companies House number"
        }
      },
      "required": ["company_number"]
    }
  }
}
```

#### Way 2: Pydantic Model (Best for Complex Inputs)

Use a Pydantic model when you have many parameters, need validation constraints, or want the richest schema.

```python
from pydantic import BaseModel, Field

class CreditDecisionInput(BaseModel):
    """Input for submitting a credit decision."""
    company_id: str = Field(description="Lenkie internal company identifier")
    decision: str = Field(description="Credit decision", enum=["APPROVE", "REFER", "DECLINE"])
    facility_amount: float = Field(description="Approved facility amount in GBP", gt=0, le=1_000_000)
    facility_term_months: int = Field(description="Facility term in months", ge=1, le=12)
    conditions: list[str] = Field(default=[], description="Conditions attached to the approval")
    notes: str = Field(default="", description="Free-text notes for the credit file")

@gw.tool(allowed_agents=["underwriting"])
async def submit_credit_decision(params: CreditDecisionInput) -> dict:
    """Submit a credit decision to the Lenkie platform. Requires human approval."""
    # params is already validated by Pydantic
    return {"status": "submitted", "decision_id": "dec_abc123"}
```

Generates:

```json
{
  "type": "function",
  "function": {
    "name": "submit_credit_decision",
    "description": "Submit a credit decision to the Lenkie platform. Requires human approval.",
    "parameters": {
      "type": "object",
      "properties": {
        "company_id": {
          "type": "string",
          "description": "Lenkie internal company identifier"
        },
        "decision": {
          "type": "string",
          "description": "Credit decision",
          "enum": ["APPROVE", "REFER", "DECLINE"]
        },
        "facility_amount": {
          "type": "number",
          "description": "Approved facility amount in GBP",
          "exclusiveMinimum": 0,
          "maximum": 1000000
        },
        "facility_term_months": {
          "type": "integer",
          "description": "Facility term in months",
          "minimum": 1,
          "maximum": 12
        },
        "conditions": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Conditions attached to the approval",
          "default": []
        },
        "notes": {
          "type": "string",
          "description": "Free-text notes for the credit file",
          "default": ""
        }
      },
      "required": ["company_id", "decision", "facility_amount", "facility_term_months"]
    }
  }
}
```

#### Way 3: Explicit Parameters Dict (Full Control)

Pass the JSON Schema directly when you want maximum control over what the LLM sees.

```python
@gw.tool(
    name="calculate-dscr",
    description="Calculate Debt Service Coverage Ratio from financial data",
    parameters={
        "type": "object",
        "properties": {
            "net_operating_income": {
                "type": "number",
                "description": "Annual net operating income in GBP",
            },
            "total_debt_service": {
                "type": "number",
                "description": "Annual total debt service (principal + interest) in GBP",
            },
        },
        "required": ["net_operating_income", "total_debt_service"],
    },
)
async def calculate_dscr(params: dict) -> dict:
    noi = params["net_operating_income"]
    tds = params["total_debt_service"]
    dscr = round(noi / tds, 2) if tds > 0 else None
    return {"dscr": dscr, "healthy": dscr >= 1.25 if dscr else False}
```

When `parameters` is passed explicitly, it's used as-is — no inference from the function signature.

#### Way 4: Bare Type Hints (Minimal — Quick Prototyping)

For quick prototyping, bare type hints work. The parameter name becomes the description.

```python
@gw.tool
async def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email via the company mail system."""
    ...
```

Generates a tool spec where each parameter has `type` inferred from the hint but the `description` defaults to the parameter name (`"to"`, `"subject"`, `"body"`). This works but gives the LLM less context. Upgrade to `Annotated` or Pydantic when the tool goes to production.

#### How Input Spec Generation Works (Priority Order)

```
1. Explicit `parameters={}` dict on decorator     → used as-is, no inference
2. Pydantic model as sole parameter                → model.json_schema()
3. Annotated[type, "description"] parameters       → type + description extracted
4. Bare type hints                                 → type inferred, name used as description
```

The framework always validates inputs against the schema before calling your function. If the LLM passes bad arguments, the tool returns an error to the LLM (not an exception to the user).

#### Type Hint → JSON Schema Mapping

| Python Type | JSON Schema Type | Notes |
|---|---|---|
| `str` | `string` | |
| `int` | `integer` | |
| `float` | `number` | |
| `bool` | `boolean` | |
| `list` | `array` | |
| `dict` | `object` | |
| `list[str]` | `array` of `string` | Typed arrays |
| `Optional[str]` | `string` (not required) | Optional parameters |
| `Literal["A", "B"]` | `string` with `enum: [A, B]` | Enum values |
| `str = "default"` | `string` (not required, has default) | Default values |
| `Annotated[str, "desc"]` | `string` with `description: "desc"` | Described parameters |

Parameters without defaults are `required`. Parameters with defaults or `Optional` are optional.

#### Decorator Parameters Reference

```python
@gw.tool(
    name="my-tool",                    # Override function name (default: function_name)
    description="Does something",      # Override docstring
    parameters={...},                  # Explicit JSON Schema (skips inference)
    allowed_agents=["underwriting"],   # Restrict to specific agents (default: all)
    require_approval=False,            # Require human approval before execution
)
```

All parameters are optional. The minimal version:

```python
@gw.tool
async def my_tool(query: Annotated[str, "Search query"]) -> dict:
    """Search for something."""
    return {"results": [...]}
```

### 15.6 Two Ways to Define Tools

Tools can be defined in two ways. Both are first-class — use whichever fits.

| Approach | Best For | Input Schema |
|---|---|---|
| **TOOL.md files** | HTTP calls, script tools, declarative. Git-friendly, no code | `parameters:` in YAML frontmatter |
| **`@gw.tool` decorator** | Custom logic, database access, app-coupled code | Annotated types, Pydantic, or explicit dict |

Both produce the same LLM tool spec. An agent doesn't know or care where a tool came from.

When both exist with the same name, the code-defined tool wins (allows overriding file-based tools).

### 15.7 Middleware

Standard FastAPI/Starlette middleware works because `Gateway` is a FastAPI app:

```python
from agent_gateway import Gateway
from starlette.middleware.cors import CORSMiddleware

gw = Gateway()

# Decorator style
@gw.middleware("http")
async def log_requests(request, call_next):
    print(f"→ {request.method} {request.url}")
    response = await call_next(request)
    print(f"← {response.status_code}")
    return response

# Or add_middleware style — any Starlette middleware works
gw.add_middleware(CORSMiddleware, allow_origins=["*"])

gw.run()
```

### 15.8 Mounting into an Existing FastAPI App

Already have a FastAPI app? Mount the gateway as a sub-application. Since `Gateway` is a FastAPI app, standard `mount()` works:

```python
from fastapi import FastAPI
from agent_gateway import Gateway

app = FastAPI(title="My Existing App")
gw = Gateway(workspace="./workspace")

# Mount the gateway under a prefix
app.mount("/agents", gw)

# Your existing routes stay untouched
@app.get("/api/health")
def health():
    return {"status": "ok"}
```

Now your agents live at `/agents/v1/agents/{id}/invoke` alongside your existing API.

**Or go the other way** — start with Gateway and mount your existing app:

```python
from fastapi import FastAPI
from agent_gateway import Gateway

legacy_app = FastAPI()

@legacy_app.get("/api/v1/deals")
async def deals():
    return [...]

gw = Gateway()
gw.mount("/legacy", legacy_app)

gw.run()
# Agent endpoints + legacy API, single process
```

---

## 16. CLI

### 14.1 Commands

```bash
# Scaffold a new project
agent-gateway init my-project

# Start the server
agent-gateway serve
agent-gateway serve --port 9000 --reload

# List discovered agents and skills
agent-gateway agents
agent-gateway skills

# Invoke an agent from the command line
agent-gateway invoke underwriting "Assess Acme Corp, 3 years trading, £500k revenue"

# Test a skill directly
agent-gateway skill-test companies-house-check --args '{"company_number": "12345678"}'

# Validate workspace (check for errors without starting)
agent-gateway check

# Show parsed config
agent-gateway config
```

### 14.2 `agent-gateway check`

Validates the workspace without starting the server:

```bash
$ agent-gateway check

✓ workspace/gateway.yaml — valid
✓ workspace/agents/underwriting/AGENT.md — valid
✓ workspace/agents/underwriting/SOUL.md — valid
✓ workspace/agents/underwriting/BEHAVIOR.md — valid
✓ workspace/agents/sales/AGENT.md — valid
✓ workspace/skills/companies-house-check/SKILL.md — valid (type: http)
✓ workspace/skills/risk-score/SKILL.md — valid (type: function)
✓ workspace/skills/risk-score/handler.py — valid (async handle function found)
✗ workspace/skills/broken-skill/SKILL.md — error: missing required field 'description'

7 agents/skills valid, 1 error
```

---

## 17. Persistence

### 15.1 What's Stored

The database stores **runtime state only**. Agent and skill definitions live on the filesystem.

| What | Where |
|---|---|
| Agent definitions | Filesystem (AGENT.md, BEHAVIOR.md) |
| Skill definitions | Filesystem (SKILL.md, handler.py) |
| Configuration | Filesystem (gateway.yaml, .env) |
| Execution history | Database |
| Execution steps/traces | Database |
| Audit log | Database |
| API keys (hashed) | gateway.yaml or database |

### 15.2 SQLite (Default)

Zero-config. A single file in the project root.

```yaml
persistence:
  backend: sqlite
  url: "sqlite:///agent_gateway.db"
```

### 15.3 PostgreSQL (Production)

```yaml
persistence:
  backend: postgresql
  url: "${DATABASE_URL}"
```

### 15.4 Schema

```sql
CREATE TABLE executions (
    id              TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    status          TEXT DEFAULT 'queued',
    message         TEXT NOT NULL,
    context         JSON DEFAULT '{}',
    options         JSON DEFAULT '{}',
    result          JSON,
    error           TEXT,
    usage           JSON DEFAULT '{}',
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE execution_steps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id    TEXT REFERENCES executions(id),
    step_type       TEXT NOT NULL,        -- llm_call | tool_call | tool_result
    sequence        INTEGER NOT NULL,
    data            JSON NOT NULL,
    duration_ms     INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    actor           TEXT,
    resource_type   TEXT,
    resource_id     TEXT,
    metadata        JSON DEFAULT '{}',
    ip_address      TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_executions_agent ON executions(agent_id, created_at DESC);
CREATE INDEX idx_executions_status ON executions(status);
CREATE INDEX idx_audit_log_type ON audit_log(event_type, created_at DESC);
```

### 15.5 Disabling Persistence

For serverless or ephemeral deployments:

```yaml
persistence:
  enabled: false
```

Executions still work — results are returned to the caller — but no history is kept.

---

## 18. Security

### 16.1 Secrets

- Environment variables (`${VAR}`) in SKILL.md HTTP configs are resolved at runtime
- Secrets are never included in LLM prompts or logged
- `.env` files are loaded but never committed (`.gitignore` by default)

### 16.2 Tool Isolation

- Skills can only access what's explicitly configured (HTTP URLs, handler functions)
- No shell access unless a skill is explicitly `type: script`
- Script skills run with a configurable timeout
- HTTP skills have configurable timeouts and retry limits

### 16.3 LLM Safety

- Max tool calls and iteration limits prevent runaway loops
- Output schema validation prevents malformed responses
- Approval gates for sensitive operations
- Tool permissions restrict which agents can use which skills

### 16.4 API Security

- API keys hashed with SHA-256 (if stored in database)
- CORS configurable in gateway.yaml
- Rate limiting (optional, via Redis)
- Outbound webhook HMAC signatures

---

## 19. Observability (OpenTelemetry)

OpenTelemetry is built in from day one — not bolted on later. Every agent invocation produces traces, metrics, and logs that export to any OTel-compatible backend (Jaeger, Datadog, Grafana, Honeycomb, etc.).

### 19.1 What Gets Instrumented

Every execution creates a **trace** with nested spans:

```
trace: agent.invoke (underwriting)
├── span: prompt.assemble           # Prompt construction time
├── span: llm.call                  # Each LLM round-trip
│   ├── attribute: model            # "anthropic/claude-sonnet-4-5"
│   ├── attribute: tokens.input     # 1,234
│   ├── attribute: tokens.output    # 567
│   └── attribute: cost_usd         # 0.0042
├── span: tool.execute              # Each tool call
│   ├── attribute: tool.name        # "companies-house-check"
│   ├── attribute: tool.type        # "http" | "function" | "script"
│   └── attribute: tool.status      # "success" | "error"
├── span: llm.call                  # Second LLM round-trip
├── span: tool.execute              # Another tool call
├── span: llm.call                  # Final LLM round-trip
├── span: output.validate           # Schema validation
└── span: notification.send         # Slack/Teams/webhook
    └── attribute: channel          # "slack"
```

### 19.2 Metrics

Automatic counters and histograms:

| Metric | Type | Description |
|---|---|---|
| `agw.executions.total` | Counter | Total invocations by agent, status |
| `agw.executions.duration_ms` | Histogram | End-to-end execution time |
| `agw.llm.calls.total` | Counter | LLM calls by agent, model, status |
| `agw.llm.duration_ms` | Histogram | Per-call LLM latency |
| `agw.llm.tokens.input` | Counter | Input tokens by agent, model |
| `agw.llm.tokens.output` | Counter | Output tokens by agent, model |
| `agw.llm.cost_usd` | Counter | Estimated cost by agent, model |
| `agw.llm.failover.total` | Counter | Model failover events |
| `agw.tools.calls.total` | Counter | Tool calls by tool, agent, status |
| `agw.tools.duration_ms` | Histogram | Per-tool execution time |
| `agw.tools.errors.total` | Counter | Tool errors by tool, error type |

### 19.3 Configuration

```yaml
# gateway.yaml
telemetry:
  enabled: true                          # true by default
  service_name: "agent-gateway"          # OTel service name
  exporter: "otlp"                       # otlp | console | none
  endpoint: "http://localhost:4317"       # OTel collector endpoint
  protocol: "grpc"                       # grpc | http
  sample_rate: 1.0                       # 1.0 = trace everything
```

Environment variables work too (standard OTel env vars are respected):

```bash
OTEL_SERVICE_NAME=agent-gateway
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1              # Sample 10% in production
```

### 19.4 Zero-Config Default

With `telemetry.enabled: true` (the default) and no exporter configured, traces go to **console** in development — you see a readable summary of every execution in your terminal:

```
[TRACE] agent=underwriting execution=exec_abc123 duration=3.2s
  ├── llm.call model=claude-sonnet-4-5 tokens=1234/567 cost=$0.0042 (1.8s)
  ├── tool.execute tool=companies-house-check status=success (0.4s)
  ├── llm.call model=claude-sonnet-4-5 tokens=890/234 cost=$0.0018 (1.2s)
  └── notification.send channel=slack status=sent (0.1s)
```

Set `OTEL_EXPORTER_OTLP_ENDPOINT` and it automatically switches to OTLP export — no code changes, no config changes.

### 19.5 Trace Context Propagation

Incoming requests with `traceparent` headers (W3C Trace Context) are respected. This means if your application already has tracing, agent-gateway spans nest under your existing traces:

```python
# Your app's trace continues into agent-gateway
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/v1/agents/underwriting/invoke",
        json={"message": "Assess Acme Corp"},
        headers={"traceparent": "00-abc123-def456-01"},  # Propagated
    )
```

### 19.6 Custom Spans in Tools

Tools registered with `@gw.tool` can add their own spans:

```python
from agent_gateway import Gateway
from opentelemetry import trace

gw = Gateway()
tracer = trace.get_tracer("my-tools")

@gw.tool()
async def companies_house_check(company_number: Annotated[str, "8-digit number"]) -> dict:
    """Query Companies House API."""
    with tracer.start_as_current_span("companies_house.api_call") as span:
        span.set_attribute("company_number", company_number)
        response = await httpx.AsyncClient().get(f"https://api.company-information.service.gov.uk/company/{company_number}")
        span.set_attribute("http.status_code", response.status_code)
        return response.json()
```

These custom spans nest under the `tool.execute` span automatically.

### 19.7 LLM-Specific Attributes

LLM spans follow the [OpenTelemetry Semantic Conventions for GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/) where applicable:

| Attribute | Example |
|---|---|
| `gen_ai.system` | `"anthropic"` |
| `gen_ai.request.model` | `"claude-sonnet-4-5-20250929"` |
| `gen_ai.response.model` | `"claude-sonnet-4-5-20250929"` |
| `gen_ai.usage.input_tokens` | `1234` |
| `gen_ai.usage.output_tokens` | `567` |
| `gen_ai.request.temperature` | `0.1` |
| `gen_ai.request.max_tokens` | `4096` |

---

## 20. Package Structure

```
agent-gateway/                         # The pip package
├── src/
│   └── agent_gateway/
│       ├── __init__.py                # Public API: Gateway, tool decorator
│       ├── gateway.py                 # Gateway(FastAPI) subclass
│       ├── config.py                  # Settings (Pydantic BaseSettings)
│       │
│       ├── workspace/                 # Workspace scanning and parsing
│       │   ├── __init__.py
│       │   ├── loader.py              # Scan dirs, discover agents/skills
│       │   ├── agent.py               # Agent model (from AGENT.md + BEHAVIOR.md)
│       │   ├── skill.py               # Skill model (from SKILL.md)
│       │   ├── prompt.py              # Prompt assembly (layered markdown)
│       │   ├── watcher.py             # File watcher for hot-reload
│       │   └── parser.py              # Markdown + YAML frontmatter parser
│       │
│       ├── api/                       # HTTP layer
│       │   ├── __init__.py
│       │   ├── app.py                 # FastAPI app factory
│       │   ├── routes/
│       │   │   ├── invoke.py          # POST /v1/agents/{id}/invoke
│       │   │   ├── executions.py      # Execution CRUD
│       │   │   ├── introspection.py   # GET /v1/agents, /v1/skills
│       │   │   ├── hooks.py           # Inbound webhooks
│       │   │   └── health.py          # Health check
│       │   └── middleware/
│       │       ├── auth.py            # API key / custom auth
│       │       ├── rate_limit.py      # Optional rate limiting
│       │       └── cors.py            # CORS
│       │
│       ├── engine/                    # Execution engine
│       │   ├── __init__.py
│       │   ├── executor.py            # LLM function-calling loop
│       │   ├── llm.py                 # LiteLLM wrapper
│       │   ├── output.py              # Structured output parsing
│       │   └── approval.py            # Approval gate logic
│       │
│       ├── skills/                    # Skill executors
│       │   ├── __init__.py
│       │   ├── runner.py              # Dispatch to correct executor
│       │   ├── http.py                # HTTP skill executor
│       │   ├── function.py            # Python function executor
│       │   └── script.py              # Script executor
│       │
│       ├── notifications/             # Outbound notifications
│       │   ├── __init__.py
│       │   ├── engine.py              # Dispatch + retry
│       │   ├── slack.py               # Slack adapter
│       │   ├── teams.py               # Teams adapter
│       │   └── webhook.py             # Generic webhook adapter
│       │
│       ├── persistence/               # Database layer
│       │   ├── __init__.py
│       │   ├── models.py              # SQLAlchemy models
│       │   ├── session.py             # DB session management
│       │   └── migrations/            # Alembic migrations
│       │
│       ├── telemetry/                 # OpenTelemetry instrumentation
│       │   ├── __init__.py            # setup_telemetry() bootstrap
│       │   ├── tracing.py             # Tracer provider + span helpers
│       │   ├── metrics.py             # Meter provider + metric definitions
│       │   └── attributes.py          # Semantic convention constants
│       │
│       └── cli/                       # CLI commands
│           ├── __init__.py
│           ├── main.py                # Click/Typer entry point
│           ├── init.py                # agent-gateway init
│           ├── serve.py               # agent-gateway serve
│           ├── invoke.py              # agent-gateway invoke
│           └── check.py              # agent-gateway check
│
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   └── workspace/                # Test workspace
│   │       ├── agents/
│   │       │   └── test-agent/
│   │       │       └── AGENT.md
│   │       └── skills/
│   │           └── test-skill/
│   │               └── SKILL.md
│   ├── test_workspace/
│   ├── test_engine/
│   ├── test_api/
│   ├── test_skills/
│   └── test_notifications/
│
├── pyproject.toml
├── LICENSE
└── README.md
```

---

## 21. Implementation Plan

### Phase 1: Core (Weeks 1-3)

**Goal**: `pip install`, define agents as markdown, invoke via API.

| Task | Effort |
|---|---|
| Package scaffolding (pyproject.toml, src layout) | 1 day |
| Workspace loader (scan dirs, parse AGENT.md/BEHAVIOR.md/SKILL.md) | 3 days |
| Prompt assembly (layered markdown merge) | 1 day |
| LLM client (LiteLLM wrapper with failover) | 2 days |
| Execution engine (function-calling loop) | 3 days |
| OpenTelemetry bootstrap (traces + metrics + console exporter) | 2 days |
| Skill executors (HTTP, function, LLM-only) | 3 days |
| FastAPI app with invoke endpoint | 2 days |
| SQLite persistence (executions table) | 1 day |
| CLI: `init`, `serve`, `invoke` | 2 days |
| Tests | 2 days |

**Deliverable**: A working pip package. Define agents as markdown, start the server, invoke via `POST /v1/agents/{id}/invoke`.

### Phase 2: Production Features (Weeks 4-6)

**Goal**: Auth, notifications, structured output, async execution.

| Task | Effort |
|---|---|
| API key auth middleware | 2 days |
| Structured output (schema validation, retry) | 2 days |
| Slack notifications | 2 days |
| Teams notifications | 1 day |
| Generic webhook notifications (HMAC signing) | 2 days |
| Async execution (background tasks) | 2 days |
| SSE streaming | 2 days |
| Audit log | 1 day |
| Hot-reload (file watcher) | 1 day |
| PostgreSQL support | 1 day |

**Deliverable**: Production-ready auth, notifications to Slack/Teams, streaming, async mode.

### Phase 3: Polish (Weeks 7-8)

**Goal**: DX polish, advanced features, documentation.

| Task | Effort |
|---|---|
| Script skill executor | 1 day |
| Approval gates (Slack buttons + API) | 3 days |
| Batch invocation | 1 day |
| `@gw.skill()` decorator for code-defined skills | 1 day |
| `@gw.on()` event hooks | 1 day |
| Mount as sub-app (`gw.as_asgi()`) | 1 day |
| `agent-gateway check` validation command | 1 day |
| PyPI publishing setup | 1 day |
| Documentation + README | 2 days |
| Integration tests | 2 days |

**Deliverable**: Published on PyPI. Full documentation. Ready for users.

### Timeline

| Phase | Duration |
|---|---|
| Phase 1: Core | 3 weeks |
| Phase 2: Production Features | 3 weeks |
| Phase 3: Polish | 2 weeks |
| **Total** | **8 weeks** |

---

## 22. Technology Choices

| Component | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Best LLM SDK ecosystem. Target audience is Python developers |
| HTTP Framework | FastAPI | Async-native, auto OpenAPI, Pydantic validation |
| LLM Client | LiteLLM | 100+ models, unified interface, cost tracking, failover |
| Database | SQLAlchemy 2.0 | Async support, works with SQLite + PostgreSQL |
| Migrations | Alembic | Standard for SQLAlchemy |
| CLI | Typer | Clean CLI framework, built on Click |
| Slack | slack-bolt | Official Slack SDK |
| Teams | httpx | Incoming webhooks (simple HTTP POST) |
| Observability | opentelemetry-api + SDK | Vendor-neutral traces, metrics, logs |
| File watching | watchfiles | Fast, cross-platform file watcher |
| YAML parsing | PyYAML | Standard |
| Markdown parsing | python-frontmatter | YAML frontmatter extraction |
| Env files | python-dotenv | .env loading |
| Package manager | uv or Poetry | Modern Python packaging |
| Testing | pytest + pytest-asyncio | Standard |

### Dependencies (Minimal)

```toml
[project]
dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
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
    "opentelemetry-api>=1.24",
    "opentelemetry-sdk>=1.24",
    "opentelemetry-semantic-conventions>=0.45b",
]

[project.optional-dependencies]
otlp = [
    "opentelemetry-exporter-otlp-proto-grpc>=1.24",
    "opentelemetry-exporter-otlp-proto-http>=1.24",
]
slack = ["slack-bolt>=1.18"]
postgresql = ["asyncpg>=0.29", "psycopg[binary]>=3.1"]
redis = ["redis>=5.0"]
```

OTLP exporters, Slack, PostgreSQL, and Redis are optional extras:
```bash
pip install agent-gateway[otlp]              # OTLP gRPC/HTTP exporters
pip install agent-gateway[slack]
pip install agent-gateway[postgresql]
pip install agent-gateway[otlp,slack,postgresql,redis]
```

**Note**: The OTel API + SDK ship with the core package (console tracing works out of the box). The `otlp` extra adds the OTLP exporters needed to send data to collectors like Jaeger, Datadog, Grafana, etc.
