"""agent-gateway invoke — invoke an agent from the command line."""

from __future__ import annotations

import asyncio
import json

import typer

from agent_gateway.cli.formatting import OutputFormat


def invoke(
    agent_id: str = typer.Argument(help="Agent ID to invoke"),
    message: str = typer.Argument(help="Message to send"),
    workspace: str | None = typer.Option(
        None, "--workspace", "-w", help="Path to workspace directory"
    ),
    output_json: bool = typer.Option(
        False, "--json", help="Output raw JSON (use --format json instead)"
    ),
    fmt: OutputFormat = typer.Option(
        OutputFormat.table, "--format", "-f", help="Output format: table, json"
    ),
) -> None:
    """Invoke an agent and print the result."""
    from agent_gateway.workspace.loader import load_workspace

    # Resolve format conflicts
    if output_json and fmt not in (OutputFormat.table, OutputFormat.json):
        typer.echo(
            "Error: cannot use both --json and --format. Use --format json instead.",
            err=True,
        )
        raise typer.Exit(code=1)
    if fmt == OutputFormat.csv:
        typer.echo(
            "Error: CSV format is not supported for invoke. Use --format json or table.",
            err=True,
        )
        raise typer.Exit(code=1)
    effective_fmt = OutputFormat.json if output_json else fmt

    ws_path = workspace or "./workspace"
    state = load_workspace(ws_path)

    if state.errors:
        for err in state.errors:
            typer.echo(f"Error: {err}", err=True)
        raise typer.Exit(code=1)

    if agent_id not in state.agents:
        typer.echo(f"Error: agent '{agent_id}' not found.", err=True)
        typer.echo(f"Available agents: {', '.join(sorted(state.agents.keys()))}", err=True)
        raise typer.Exit(code=1)

    # Run the invocation
    result = asyncio.run(_invoke_agent(ws_path, agent_id, message))

    if effective_fmt == OutputFormat.json:
        typer.echo(json.dumps(result, indent=2))
    else:
        # Human-friendly output
        status = result.get("status", "unknown")
        typer.echo(f"Status: {status}")

        output = result.get("result", {})
        if isinstance(output, dict):
            raw_text = output.get("raw_text", "")
            if raw_text:
                typer.echo(f"\n{raw_text}")
            structured = output.get("output")
            if structured:
                typer.echo(f"\n{json.dumps(structured, indent=2)}")


async def _invoke_agent(workspace: str, agent_id: str, message: str) -> dict[str, object]:
    """Run the agent invocation via Gateway.invoke()."""
    from agent_gateway.gateway import Gateway

    async with Gateway(workspace=workspace, auth=False) as gw:
        try:
            result = await gw.invoke(agent_id, message)
            return {
                "status": result.stop_reason.value,
                "result": result.to_dict(),
            }
        except ValueError as e:
            return {
                "status": "error",
                "result": {"raw_text": str(e)},
            }
        except Exception as e:
            return {
                "status": "error",
                "result": {"raw_text": f"Invocation failed: {e}"},
            }
