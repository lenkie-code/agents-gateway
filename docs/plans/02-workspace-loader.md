---
title: "Phase 1.2: Workspace Loader"
type: feat
status: pending
date: 2026-02-18
depends_on: [01]
blocks: [03, 04, 08]
parent: 2026-02-18-feat-agent-gateway-framework-plan.md
---

# Phase 1.2: Workspace Loader

## Goal

Parse the workspace filesystem — discover agents, skills, tools, and schedules from markdown files. Assemble layered system prompts. After this phase, `WorkspaceLoader.load("./workspace")` returns a fully parsed `WorkspaceState` with all definitions, cross-references validated, and prompts assembled.

## Prerequisites

- Phase 01 complete (package structure, config, exceptions)

---

## Tasks

### 1. Markdown + YAML Frontmatter Parser

**File:** `src/agent_gateway/workspace/parser.py`

Wraps `python-frontmatter` with error handling for the specific patterns used in Agent Gateway.

```python
"""Parse markdown files with optional YAML frontmatter."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter

logger = logging.getLogger(__name__)


@dataclass
class ParsedMarkdown:
    """Result of parsing a markdown file."""
    content: str                           # Markdown body (no frontmatter)
    metadata: dict[str, Any] = field(default_factory=dict)  # YAML frontmatter
    path: Path | None = None               # Source file path


def parse_markdown_file(path: Path) -> ParsedMarkdown:
    """Parse a markdown file, extracting YAML frontmatter if present.

    Handles:
    - Files with frontmatter (---\nyaml\n---\nmarkdown)
    - Files without frontmatter (plain markdown)
    - Empty files (returns empty content + metadata)
    - Invalid UTF-8 (logs warning, returns empty)
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning("Invalid UTF-8 in %s, skipping", path)
        return ParsedMarkdown(content="", path=path)

    if not text.strip():
        logger.warning("Empty file: %s", path)
        return ParsedMarkdown(content="", path=path)

    try:
        post = frontmatter.loads(text)
        return ParsedMarkdown(
            content=post.content,
            metadata=dict(post.metadata),
            path=path,
        )
    except Exception:
        logger.warning("Failed to parse frontmatter in %s, treating as plain markdown", path)
        return ParsedMarkdown(content=text, path=path)


def parse_markdown_string(text: str) -> ParsedMarkdown:
    """Parse a markdown string with optional frontmatter."""
    if not text.strip():
        return ParsedMarkdown(content="")
    try:
        post = frontmatter.loads(text)
        return ParsedMarkdown(content=post.content, metadata=dict(post.metadata))
    except Exception:
        return ParsedMarkdown(content=text)
```

### 2. Agent Model

**File:** `src/agent_gateway/workspace/agent.py`

```python
"""Agent model — loaded from AGENT.md + SOUL.md + CONFIG.md."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_gateway.workspace.parser import ParsedMarkdown, parse_markdown_file

logger = logging.getLogger(__name__)


@dataclass
class ScheduleConfig:
    """A cron schedule for an agent."""
    name: str
    cron: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    timezone: str = "UTC"


@dataclass
class AgentModelConfig:
    """Per-agent model configuration from CONFIG.md."""
    name: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    fallback: str | None = None


@dataclass
class AgentDefinition:
    """A fully parsed agent definition."""
    id: str                                     # Directory name (e.g., "underwriting")
    path: Path                                  # Directory path
    agent_prompt: str                           # Content of AGENT.md
    soul_prompt: str = ""                       # Content of SOUL.md (optional)
    config_metadata: dict[str, Any] = field(default_factory=dict)  # CONFIG.md frontmatter
    config_doc: str = ""                        # CONFIG.md markdown body

    # Parsed from CONFIG.md frontmatter
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    model: AgentModelConfig = field(default_factory=AgentModelConfig)
    guardrails: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    notifications: dict[str, Any] = field(default_factory=dict)
    schedules: list[ScheduleConfig] = field(default_factory=list)

    @classmethod
    def load(cls, agent_dir: Path) -> AgentDefinition | None:
        """Load an agent from a directory.

        Returns None if AGENT.md is missing (not a valid agent dir).
        """
        agent_md = agent_dir / "AGENT.md"
        if not agent_md.exists():
            return None

        agent_id = agent_dir.name

        # Parse AGENT.md (required)
        agent_parsed = parse_markdown_file(agent_md)
        if not agent_parsed.content.strip():
            logger.warning("Empty AGENT.md in %s, skipping agent", agent_dir)
            return None

        # Parse SOUL.md (optional)
        soul_md = agent_dir / "SOUL.md"
        soul_prompt = ""
        if soul_md.exists():
            soul_parsed = parse_markdown_file(soul_md)
            soul_prompt = soul_parsed.content

        # Parse CONFIG.md (optional)
        config_md = agent_dir / "CONFIG.md"
        config_metadata: dict[str, Any] = {}
        config_doc = ""
        if config_md.exists():
            config_parsed = parse_markdown_file(config_md)
            config_metadata = config_parsed.metadata
            config_doc = config_parsed.content

        # Extract typed fields from config metadata
        model_data = config_metadata.get("model", {})
        model_config = AgentModelConfig(
            name=model_data.get("name"),
            temperature=model_data.get("temperature"),
            max_tokens=model_data.get("max_tokens"),
            fallback=model_data.get("fallback"),
        )

        schedules_data = config_metadata.get("schedules", [])
        schedules = []
        for s in schedules_data:
            try:
                schedules.append(ScheduleConfig(
                    name=s["name"],
                    cron=s["cron"],
                    message=s["message"],
                    context=s.get("context", {}),
                    enabled=s.get("enabled", True),
                    timezone=s.get("timezone", "UTC"),
                ))
            except (KeyError, TypeError) as e:
                logger.warning("Invalid schedule in %s: %s", agent_dir, e)

        return cls(
            id=agent_id,
            path=agent_dir,
            agent_prompt=agent_parsed.content,
            soul_prompt=soul_prompt,
            config_metadata=config_metadata,
            config_doc=config_doc,
            skills=config_metadata.get("skills", []),
            tools=config_metadata.get("tools", []),
            model=model_config,
            guardrails=config_metadata.get("guardrails", {}),
            output_schema=config_metadata.get("output_schema"),
            notifications=config_metadata.get("notifications", {}),
            schedules=schedules,
        )
```

### 3. Skill Model

**File:** `src/agent_gateway/workspace/skill.py`

```python
"""Skill model — loaded from SKILL.md."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_gateway.workspace.parser import parse_markdown_file

logger = logging.getLogger(__name__)


@dataclass
class SkillDefinition:
    """A fully parsed skill definition."""
    id: str                                  # Directory name
    path: Path                               # Directory path
    name: str                                # From frontmatter
    description: str                         # From frontmatter
    tools: list[str] = field(default_factory=list)  # Tool names this skill uses
    version: str = "1.0.0"
    instructions: str = ""                   # Markdown body (injected into prompt)

    @classmethod
    def load(cls, skill_dir: Path) -> SkillDefinition | None:
        """Load a skill from a directory. Returns None if SKILL.md missing."""
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return None

        parsed = parse_markdown_file(skill_md)
        meta = parsed.metadata

        name = meta.get("name", skill_dir.name)
        description = meta.get("description", "")

        if not description:
            logger.warning("Skill %s has no description", skill_dir.name)

        return cls(
            id=skill_dir.name,
            path=skill_dir,
            name=name,
            description=description,
            tools=meta.get("tools", []),
            version=meta.get("version", "1.0.0"),
            instructions=parsed.content,
        )
```

### 4. Tool Model (File-Based)

**File:** `src/agent_gateway/workspace/tool.py`

```python
"""Tool model — loaded from TOOL.md."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_gateway.workspace.parser import parse_markdown_file

logger = logging.getLogger(__name__)


@dataclass
class HttpConfig:
    """HTTP tool configuration."""
    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    timeout_ms: int = 15_000


@dataclass
class ScriptConfig:
    """Script tool configuration."""
    command: str = ""
    timeout_ms: int = 30_000


@dataclass
class ToolParameter:
    """A single tool parameter."""
    name: str
    type: str = "string"
    description: str = ""
    required: bool = False
    enum: list[str] | None = None
    default: Any = None


@dataclass
class ToolDefinition:
    """A fully parsed file-based tool definition."""
    id: str                                  # Directory name
    path: Path                               # Directory path
    name: str                                # From frontmatter
    description: str                         # From frontmatter
    type: str = "function"                   # http | function | script
    parameters: list[ToolParameter] = field(default_factory=list)
    http: HttpConfig | None = None
    script: ScriptConfig | None = None
    permissions: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    instructions: str = ""                   # Markdown body
    handler_path: Path | None = None         # Path to handler.py (for function tools)
    is_broken: bool = False                  # Set if handler has import errors
    error_message: str = ""                  # Why the tool is broken

    @classmethod
    def load(cls, tool_dir: Path) -> ToolDefinition | None:
        """Load a tool from a directory. Returns None if TOOL.md missing."""
        tool_md = tool_dir / "TOOL.md"
        if not tool_md.exists():
            return None

        parsed = parse_markdown_file(tool_md)
        meta = parsed.metadata

        name = meta.get("name", tool_dir.name)
        description = meta.get("description", "")
        tool_type = meta.get("type", "function")

        if not description:
            logger.warning("Tool %s has no description", tool_dir.name)

        # Parse parameters
        params_data = meta.get("parameters", {})
        parameters = []
        for param_name, param_def in params_data.items():
            if isinstance(param_def, dict):
                parameters.append(ToolParameter(
                    name=param_name,
                    type=param_def.get("type", "string"),
                    description=param_def.get("description", param_name),
                    required=param_def.get("required", False),
                    enum=param_def.get("enum"),
                    default=param_def.get("default"),
                ))

        # Parse HTTP config
        http_config = None
        if tool_type == "http":
            http_data = meta.get("http", {})
            http_config = HttpConfig(
                method=http_data.get("method", "GET"),
                url=http_data.get("url", ""),
                headers=http_data.get("headers", {}),
                body=http_data.get("body"),
                timeout_ms=http_data.get("timeout_ms", 15_000),
            )

        # Parse script config
        script_config = None
        if tool_type == "script":
            script_data = meta.get("script", {})
            script_config = ScriptConfig(
                command=script_data.get("command", ""),
                timeout_ms=script_data.get("timeout_ms", 30_000),
            )

        # Check for handler.py (function tools)
        handler_path = tool_dir / "handler.py"
        has_handler = handler_path.exists() if tool_type == "function" else False

        return cls(
            id=tool_dir.name,
            path=tool_dir,
            name=name,
            description=description,
            type=tool_type,
            parameters=parameters,
            http=http_config,
            script=script_config,
            permissions=meta.get("permissions", {}),
            version=meta.get("version", "1.0.0"),
            instructions=parsed.content,
            handler_path=handler_path if has_handler else None,
        )

    def to_json_schema(self) -> dict[str, Any]:
        """Convert parameters to JSON Schema for LLM function calling."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema

    def to_llm_declaration(self) -> dict[str, Any]:
        """Convert to LLM tool declaration format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.to_json_schema(),
            },
        }
```

### 5. Workspace Loader

**File:** `src/agent_gateway/workspace/loader.py`

```python
"""Scan workspace directories and discover agents, skills, tools."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from agent_gateway.workspace.agent import AgentDefinition, ScheduleConfig
from agent_gateway.workspace.skill import SkillDefinition
from agent_gateway.workspace.tool import ToolDefinition

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceState:
    """The complete parsed state of a workspace."""
    path: Path
    agents: dict[str, AgentDefinition] = field(default_factory=dict)
    skills: dict[str, SkillDefinition] = field(default_factory=dict)
    tools: dict[str, ToolDefinition] = field(default_factory=dict)
    schedules: list[ScheduleConfig] = field(default_factory=list)
    root_system_prompt: str = ""       # From agents/AGENTS.md
    root_soul_prompt: str = ""         # From agents/SOUL.md
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @classmethod
    def empty(cls, path: Path | None = None) -> WorkspaceState:
        return cls(path=path or Path("."))


class WorkspaceLoader:
    """Discovers and loads agents, skills, and tools from a workspace directory."""

    @classmethod
    async def load(cls, workspace_path: str | Path) -> WorkspaceState:
        """Load the full workspace. Never raises — collects warnings/errors."""
        path = Path(workspace_path)
        state = WorkspaceState(path=path)

        if not path.exists():
            state.errors.append(f"Workspace directory not found: {path}")
            return state

        if not path.is_dir():
            state.errors.append(f"Workspace path is not a directory: {path}")
            return state

        # Load root prompts
        cls._load_root_prompts(path, state)

        # Discover agents, skills, tools
        cls._load_agents(path / "agents", state)
        cls._load_skills(path / "skills", state)
        cls._load_tools(path / "tools", state)

        # Collect schedules from agents
        for agent in state.agents.values():
            for schedule in agent.schedules:
                state.schedules.append(schedule)

        # Cross-reference validation (warnings only)
        cls._validate_cross_references(state)

        agent_count = len(state.agents)
        skill_count = len(state.skills)
        tool_count = len(state.tools)
        schedule_count = len(state.schedules)
        logger.info(
            "Workspace loaded: %d agents, %d skills, %d tools, %d schedules",
            agent_count, skill_count, tool_count, schedule_count,
        )

        return state

    @classmethod
    def _load_root_prompts(cls, workspace: Path, state: WorkspaceState) -> None:
        from agent_gateway.workspace.parser import parse_markdown_file

        agents_md = workspace / "agents" / "AGENTS.md"
        if agents_md.exists():
            parsed = parse_markdown_file(agents_md)
            state.root_system_prompt = parsed.content

        soul_md = workspace / "agents" / "SOUL.md"
        if soul_md.exists():
            parsed = parse_markdown_file(soul_md)
            state.root_soul_prompt = parsed.content

    @classmethod
    def _load_agents(cls, agents_dir: Path, state: WorkspaceState) -> None:
        if not agents_dir.exists():
            state.warnings.append("No agents/ directory found")
            return

        for entry in sorted(agents_dir.iterdir()):
            if not entry.is_dir():
                continue
            # Skip hidden directories
            if entry.name.startswith("."):
                continue

            agent = AgentDefinition.load(entry)
            if agent is not None:
                state.agents[agent.id] = agent
                logger.debug("Loaded agent: %s", agent.id)

    @classmethod
    def _load_skills(cls, skills_dir: Path, state: WorkspaceState) -> None:
        if not skills_dir.exists():
            return  # Skills are optional, no warning needed

        for entry in sorted(skills_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            skill = SkillDefinition.load(entry)
            if skill is not None:
                state.skills[skill.id] = skill
                logger.debug("Loaded skill: %s", skill.id)

    @classmethod
    def _load_tools(cls, tools_dir: Path, state: WorkspaceState) -> None:
        if not tools_dir.exists():
            return

        for entry in sorted(tools_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            tool = ToolDefinition.load(entry)
            if tool is not None:
                state.tools[tool.id] = tool
                logger.debug("Loaded tool: %s (%s)", tool.id, tool.type)

    @classmethod
    def _validate_cross_references(cls, state: WorkspaceState) -> None:
        """Check that skills reference existing tools, agents reference existing skills."""
        for skill in state.skills.values():
            for tool_name in skill.tools:
                if tool_name not in state.tools:
                    state.warnings.append(
                        f"Skill '{skill.id}' references unknown tool '{tool_name}'"
                    )

        for agent in state.agents.values():
            for skill_name in agent.skills:
                if skill_name not in state.skills:
                    state.warnings.append(
                        f"Agent '{agent.id}' references unknown skill '{skill_name}'"
                    )
            for tool_name in agent.tools:
                if tool_name not in state.tools:
                    state.warnings.append(
                        f"Agent '{agent.id}' references unknown tool '{tool_name}'"
                    )
```

### 6. Prompt Assembly

**File:** `src/agent_gateway/workspace/prompt.py`

```python
"""Assemble layered system prompts for agents."""

from __future__ import annotations

from agent_gateway.workspace.agent import AgentDefinition
from agent_gateway.workspace.loader import WorkspaceState
from agent_gateway.workspace.skill import SkillDefinition


def assemble_system_prompt(
    agent: AgentDefinition,
    workspace: WorkspaceState,
) -> str:
    """Build the full system prompt for an agent.

    Layer order:
    1. Root AGENTS.md (shared system context)
    2. Root SOUL.md (shared personality)
    3. Agent AGENT.md (agent-specific instructions)
    4. Agent SOUL.md (agent-specific personality)
    5. Skill instructions (from each skill the agent uses)
    6. Business context (from gateway.yaml context block)
    """
    parts: list[str] = []

    # 1. Root system prompt
    if workspace.root_system_prompt:
        parts.append(workspace.root_system_prompt)

    # 2. Root soul
    if workspace.root_soul_prompt:
        parts.append(workspace.root_soul_prompt)

    # 3. Agent prompt
    parts.append(agent.agent_prompt)

    # 4. Agent soul
    if agent.soul_prompt:
        parts.append(agent.soul_prompt)

    # 5. Skill instructions
    resolved_skills = _resolve_skills(agent, workspace)
    if resolved_skills:
        skill_section = _format_skills_section(resolved_skills)
        parts.append(skill_section)

    return "\n\n---\n\n".join(parts)


def _resolve_skills(
    agent: AgentDefinition,
    workspace: WorkspaceState,
) -> list[SkillDefinition]:
    """Resolve skill names to definitions, skipping missing ones."""
    resolved = []
    for skill_name in agent.skills:
        skill = workspace.skills.get(skill_name)
        if skill is not None:
            resolved.append(skill)
    return resolved


def _format_skills_section(skills: list[SkillDefinition]) -> str:
    """Format skill instructions for injection into the system prompt."""
    parts = ["## Available Skills\n"]
    for skill in skills:
        parts.append(f"### Skill: {skill.name}\n")
        if skill.description:
            parts.append(f"*{skill.description}*\n")
        if skill.instructions:
            parts.append(skill.instructions)
        parts.append("")
    return "\n".join(parts)
```

### 7. `src/agent_gateway/workspace/__init__.py`

```python
"""Workspace loading and parsing."""

from agent_gateway.workspace.loader import WorkspaceLoader, WorkspaceState

__all__ = ["WorkspaceLoader", "WorkspaceState"]
```

---

## Tests

**`tests/test_workspace/test_parser.py`:**

Test all parser edge cases: valid frontmatter, no frontmatter, empty file, invalid UTF-8, malformed YAML.

**`tests/test_workspace/test_agent.py`:**

Test loading agents: minimal (just AGENT.md), full (AGENT.md + SOUL.md + CONFIG.md), missing AGENT.md returns None, empty AGENT.md returns None, CONFIG.md with schedules, CONFIG.md with model config.

**`tests/test_workspace/test_skill.py`:**

Test loading skills: with tools list, without tools, missing SKILL.md returns None, missing description warns.

**`tests/test_workspace/test_tool.py`:**

Test loading tools: HTTP type with config, function type with handler.py, script type, parameter parsing, `to_json_schema()`, `to_llm_declaration()`.

**`tests/test_workspace/test_loader.py`:**

Test full workspace loading: fixture workspace loads correctly, missing workspace dir collects error, cross-reference warnings, empty workspace, agent count.

**`tests/test_workspace/test_prompt.py`:**

Test prompt assembly: layered concatenation, skills injected, missing skills skipped, root prompts included.

---

## Acceptance Criteria

- [ ] `WorkspaceLoader.load("tests/fixtures/workspace")` returns a valid `WorkspaceState`
- [ ] Agents, skills, tools all parsed with correct fields
- [ ] Invalid files produce warnings, not crashes
- [ ] Cross-reference warnings generated for missing tools/skills
- [ ] Prompt assembly produces correct layered output
- [ ] Schedule definitions parsed from CONFIG.md
- [ ] All edge cases tested (empty files, missing dirs, bad UTF-8)
- [ ] `uv run pytest tests/test_workspace/` passes
