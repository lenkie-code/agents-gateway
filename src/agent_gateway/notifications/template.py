"""Jinja2 template rendering for notification payloads.

Uses SandboxedEnvironment to prevent Server-Side Template Injection (SSTI).
Environments are cached as module-level singletons to avoid repeated allocation.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, FileSystemLoader, select_autoescape
from jinja2.sandbox import SandboxedEnvironment

_AUTOESCAPE = select_autoescape(default=False, default_for_string=False)


def _make_env(loader: BaseLoader | FileSystemLoader) -> SandboxedEnvironment:
    env = SandboxedEnvironment(loader=loader, autoescape=_AUTOESCAPE)
    env.filters["tojson"] = lambda v: json.dumps(v, default=str)
    return env


# Cached environments — one per loader type
_string_env: SandboxedEnvironment | None = None
_file_envs: dict[str, SandboxedEnvironment] = {}


def _get_string_env() -> SandboxedEnvironment:
    global _string_env
    if _string_env is None:
        _string_env = _make_env(BaseLoader())
    return _string_env


def _get_file_env(directory: str) -> SandboxedEnvironment:
    if directory not in _file_envs:
        _file_envs[directory] = _make_env(FileSystemLoader(directory))
    return _file_envs[directory]


def render_template(path: Path, **context: Any) -> str:
    """Render a Jinja2 template file with the given context."""
    env = _get_file_env(str(path.parent))
    template = env.get_template(path.name)
    return template.render(**context)


@functools.lru_cache(maxsize=64)
def _compile_string(source: str) -> Any:
    """Cache compiled templates by source string."""
    return _get_string_env().from_string(source)


def render_template_string(source: str, **context: Any) -> str:
    """Render an inline Jinja2 template string."""
    template = _compile_string(source)
    return str(template.render(**context))
