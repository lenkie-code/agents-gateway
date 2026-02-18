"""Skill model — loaded from SKILL.md."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

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
