"""Agent model — loaded from AGENT.md + SOUL.md + CONFIG.md."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_gateway.workspace.parser import parse_markdown_file

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
