"""Input resolver for workflow step templates.

Resolves JSONPath-like references in step input templates against a
runtime context. Supports references like:

- ``$.input.company_name`` — value from the workflow input
- ``$.steps.enrich.output`` — output of a previous step
- ``$.steps.score[0].output`` — output of the first tool in a parallel step
"""

from __future__ import annotations

import re
from typing import Any

_REF_PATTERN = re.compile(r"^\$\.(input|steps)\.(.+)$")


def resolve_input(template: dict[str, str], context: dict[str, Any]) -> dict[str, Any]:
    """Resolve a step's input template against the workflow context.

    Args:
        template: Mapping of param names to either literal values or
            ``$.``-prefixed references.
        context: Runtime context with ``input`` and ``steps`` keys.

    Returns:
        Resolved input dict ready for tool invocation.
    """
    resolved: dict[str, Any] = {}
    for key, value in template.items():
        resolved[key] = _resolve_value(value, context)
    return resolved


def _resolve_value(value: str, context: dict[str, Any]) -> Any:
    """Resolve a single value — either a ``$.`` reference or a literal."""
    match = _REF_PATTERN.match(value)
    if match is None:
        return value  # Literal string

    root = match.group(1)  # "input" or "steps"
    path = match.group(2)  # e.g. "company_name" or "enrich.output" or "score[0].output"

    obj = context.get(root)
    if obj is None:
        return None

    return _navigate(obj, path)


def _navigate(obj: Any, path: str) -> Any:
    """Navigate a dotted path with optional array indexing.

    Supports paths like:
    - ``company_name`` — simple key lookup
    - ``enrich.output`` — nested key lookup
    - ``score[0].output`` — array index then key lookup
    """
    segments = _split_path(path)
    current = obj

    for segment in segments:
        if current is None:
            return None

        # Check for array index: "name[0]"
        bracket_match = re.match(r"^(\w+)\[(\d+)\]$", segment)
        if bracket_match:
            key = bracket_match.group(1)
            index = int(bracket_match.group(2))
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
            if isinstance(current, list) and 0 <= index < len(current):
                current = current[index]
            else:
                return None
        elif isinstance(current, dict):
            current = current.get(segment)
        else:
            return None

    return current


def _split_path(path: str) -> list[str]:
    """Split a dotted path, respecting brackets.

    ``"enrich.output"`` → ``["enrich", "output"]``
    ``"score[0].output"`` → ``["score[0]", "output"]``
    """
    return path.split(".")
