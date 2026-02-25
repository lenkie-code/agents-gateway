"""Output formatting helpers for CLI commands."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from enum import StrEnum
from typing import Any


class OutputFormat(StrEnum):
    """Supported CLI output formats."""

    table = "table"
    json = "json"
    csv = "csv"


def render_json(rows: list[dict[str, Any]]) -> str:
    """Render rows as a JSON array."""
    return json.dumps(rows, indent=2)


def render_csv(rows: list[dict[str, Any]], columns: list[str]) -> str:
    """Render rows as CSV with header. Empty rows produce header-only output."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().rstrip("\r\n").replace("\r\n", "\n")


def output_formatted(
    rows: list[dict[str, Any]],
    fmt: OutputFormat,
    columns: list[str],
    table_fn: Callable[[list[dict[str, Any]]], None],
) -> None:
    """Dispatch output to the appropriate renderer."""
    import typer

    if fmt == OutputFormat.json:
        typer.echo(render_json(rows))
    elif fmt == OutputFormat.csv:
        typer.echo(render_csv(rows, columns))
    else:
        table_fn(rows)
