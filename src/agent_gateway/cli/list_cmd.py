"""agent-gateway agents/skills/schedules — list discovered resources."""

from __future__ import annotations

from typing import Any

import typer

from agent_gateway.cli.formatting import OutputFormat, output_formatted
from agent_gateway.workspace.loader import WorkspaceState


def _load_state(workspace: str | None) -> WorkspaceState:
    from agent_gateway.workspace.loader import load_workspace

    ws_path = workspace or "./workspace"
    state = load_workspace(ws_path)

    if state.errors:
        for err in state.errors:
            typer.echo(f"Error: {err}", err=True)
        raise typer.Exit(code=1)

    return state


def agents(
    workspace: str | None = typer.Option(
        None, "--workspace", "-w", help="Path to workspace directory"
    ),
    fmt: OutputFormat = typer.Option(
        OutputFormat.table, "--format", "-f", help="Output format: table, json, csv"
    ),
) -> None:
    """List all discovered agents."""
    state = _load_state(workspace)

    columns = ["id", "skills", "tools", "model"]

    rows: list[dict[str, Any]] = []
    for agent_id, agent in sorted(state.agents.items()):
        model = agent.model.name or "(default)"
        tool_count = sum(len(state.skills[s].tools) for s in agent.skills if s in state.skills)
        rows.append(
            {
                "id": agent_id,
                "skills": len(agent.skills),
                "tools": tool_count,
                "model": model,
            }
        )

    def _table(r: list[dict[str, Any]]) -> None:
        if not r:
            typer.echo("No agents found.")
            return
        typer.echo(f"{'ID':<25} {'Skills':<8} {'Tools':<8} {'Model':<25}")
        typer.echo("-" * 66)
        for row in r:
            typer.echo(f"{row['id']:<25} {row['skills']:<8} {row['tools']:<8} {row['model']:<25}")

    output_formatted(rows, fmt, columns, _table)


def skills(
    workspace: str | None = typer.Option(
        None, "--workspace", "-w", help="Path to workspace directory"
    ),
    fmt: OutputFormat = typer.Option(
        OutputFormat.table, "--format", "-f", help="Output format: table, json, csv"
    ),
) -> None:
    """List all discovered skills."""
    state = _load_state(workspace)

    columns = ["id", "tools", "steps", "description"]

    rows: list[dict[str, Any]] = []
    for skill_id, skill in sorted(state.skills.items()):
        tools_list = ", ".join(skill.tools) if skill.tools else ""
        step_count = len(skill.steps) if skill.steps else 0
        desc = skill.description or ""
        rows.append(
            {
                "id": skill_id,
                "tools": tools_list,
                "steps": step_count,
                "description": desc,
            }
        )

    def _table(r: list[dict[str, Any]]) -> None:
        if not r:
            typer.echo("No skills found.")
            return
        typer.echo(f"{'ID':<25} {'Tools':<25} {'Steps':<8} {'Description':<35}")
        typer.echo("-" * 93)
        for row in r:
            tools_str = row["tools"] or "(none)"
            if len(tools_str) > 24:
                tools_str = tools_str[:21] + "..."
            step_str = str(row["steps"]) if row["steps"] else "-"
            desc = row["description"][:35]
            typer.echo(f"{row['id']:<25} {tools_str:<25} {step_str:<8} {desc:<35}")

    output_formatted(rows, fmt, columns, _table)


def schedules(
    workspace: str | None = typer.Option(
        None, "--workspace", "-w", help="Path to workspace directory"
    ),
    fmt: OutputFormat = typer.Option(
        OutputFormat.table, "--format", "-f", help="Output format: table, json, csv"
    ),
) -> None:
    """List all discovered schedules."""
    state = _load_state(workspace)

    columns = ["name", "agent", "cron", "enabled", "timezone"]

    rows: list[dict[str, Any]] = []
    for sched in state.schedules:
        agent_id = "(unknown)"
        for aid, agent in state.agents.items():
            if sched in agent.schedules:
                agent_id = aid
                break
        rows.append(
            {
                "name": sched.name,
                "agent": agent_id,
                "cron": sched.cron,
                "enabled": sched.enabled,
                "timezone": sched.timezone or "UTC",
            }
        )

    def _table(r: list[dict[str, Any]]) -> None:
        if not r:
            typer.echo("No schedules found.")
            return
        typer.echo(f"{'Name':<30} {'Agent':<20} {'Cron':<20} {'Enabled':<8} {'Timezone':<15}")
        typer.echo("-" * 93)
        for row in r:
            enabled = "yes" if row["enabled"] else "no"
            typer.echo(
                f"{row['name']:<30} {row['agent']:<20} {row['cron']:<20} "
                f"{enabled:<8} {row['timezone']:<15}"
            )

    output_formatted(rows, fmt, columns, _table)
