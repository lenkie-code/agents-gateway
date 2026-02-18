"""Agent Gateway CLI."""

import typer

app = typer.Typer(
    name="agent-gateway",
    help="An opinionated FastAPI extension for building API-first AI agent services.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Show the agent-gateway version."""
    from agent_gateway import __version__

    typer.echo(f"agent-gateway {__version__}")
