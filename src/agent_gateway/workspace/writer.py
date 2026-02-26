"""Utility for updating AGENT.md frontmatter while preserving the markdown body."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import yaml

from agent_gateway.exceptions import AgentGatewayError
from agent_gateway.workspace.parser import parse_markdown_file


class AgentWriteError(AgentGatewayError):
    """Raised when writing to AGENT.md fails."""


def update_agent_frontmatter(agent_dir: Path, updates: dict[str, Any]) -> None:
    """Update specific frontmatter fields in AGENT.md, preserving body content.

    Only updates fields present in ``updates``. Does not remove existing fields.
    Uses atomic write (temp file + rename) to prevent corruption.
    """
    agent_md = agent_dir / "AGENT.md"
    if not agent_md.exists():
        raise AgentWriteError(f"AGENT.md not found in {agent_dir}")

    parsed = parse_markdown_file(agent_md)
    metadata = dict(parsed.metadata)  # copy existing frontmatter

    # Merge updates (shallow for top-level, deep-merge for 'model')
    for key, value in updates.items():
        if key == "model" and isinstance(value, dict) and isinstance(metadata.get("model"), dict):
            metadata["model"] = {**metadata["model"], **value}
        else:
            metadata[key] = value

    # Serialize
    frontmatter = yaml.dump(
        metadata,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    content = f"---\n{frontmatter}---\n\n{parsed.content}"

    # Atomic write
    fd, tmp_path = tempfile.mkstemp(dir=agent_dir, suffix=".md.tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp_path).replace(agent_md)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise
