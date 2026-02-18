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

        if not path.exists():  # noqa: ASYNC240
            state.errors.append(f"Workspace directory not found: {path}")
            return state

        if not path.is_dir():  # noqa: ASYNC240
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
