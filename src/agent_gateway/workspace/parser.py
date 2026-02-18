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
