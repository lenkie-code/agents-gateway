"""Jinja2 template rendering for notification payloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_template(path: Path, **context: Any) -> str:
    """Render a Jinja2 template file with the given context."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(path.parent),
        autoescape=select_autoescape([]),
    )
    env.filters["tojson"] = lambda v: json.dumps(v, default=str)
    template = env.get_template(path.name)
    return template.render(**context)


def render_template_string(source: str, **context: Any) -> str:
    """Render an inline Jinja2 template string."""
    from jinja2 import BaseLoader, Environment, select_autoescape

    env = Environment(
        loader=BaseLoader(),
        autoescape=select_autoescape([]),
    )
    env.filters["tojson"] = lambda v: json.dumps(v, default=str)
    template = env.from_string(source)
    return template.render(**context)
