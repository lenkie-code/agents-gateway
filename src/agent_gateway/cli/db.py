"""agent-gateway db — database migration commands."""

from __future__ import annotations

from pathlib import Path

import typer

db_app = typer.Typer(
    name="db",
    help="Database migration commands.",
    no_args_is_help=True,
)


def _get_db_url(workspace: str | None) -> str:
    """Resolve the database URL from gateway config."""
    from agent_gateway.config import GatewayConfig

    ws_path = workspace or "./workspace"
    config = GatewayConfig.load(Path(ws_path))
    url = config.persistence.url
    if not url:
        typer.echo("Error: No persistence.url configured.", err=True)
        raise typer.Exit(code=1)
    return url


def _normalize_url(url: str) -> str:
    """Convert async driver URLs to sync equivalents for Alembic."""
    url = url.replace("sqlite+aiosqlite://", "sqlite://")
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    return url


@db_app.command()
def upgrade(
    revision: str = typer.Argument("head", help="Target revision (default: head)"),
    workspace: str | None = typer.Option(
        None, "--workspace", "-w", help="Path to workspace directory"
    ),
) -> None:
    """Apply database migrations up to the target revision."""
    from alembic import command

    from agent_gateway.persistence.migrations.runner import get_config_for_url

    url = _normalize_url(_get_db_url(workspace))
    cfg = get_config_for_url(url)
    command.upgrade(cfg, revision)
    typer.echo(f"Upgraded to {revision}")


@db_app.command()
def downgrade(
    revision: str = typer.Argument("-1", help="Target revision (default: -1)"),
    workspace: str | None = typer.Option(
        None, "--workspace", "-w", help="Path to workspace directory"
    ),
) -> None:
    """Roll back database migrations to the target revision."""
    from alembic import command

    from agent_gateway.persistence.migrations.runner import get_config_for_url

    url = _normalize_url(_get_db_url(workspace))
    cfg = get_config_for_url(url)
    command.downgrade(cfg, revision)
    typer.echo(f"Downgraded to {revision}")


@db_app.command()
def current(
    workspace: str | None = typer.Option(
        None, "--workspace", "-w", help="Path to workspace directory"
    ),
) -> None:
    """Show the current migration revision."""
    from alembic import command

    from agent_gateway.persistence.migrations.runner import get_config_for_url

    url = _normalize_url(_get_db_url(workspace))
    cfg = get_config_for_url(url)
    command.current(cfg, verbose=True)


@db_app.command()
def history(
    workspace: str | None = typer.Option(
        None, "--workspace", "-w", help="Path to workspace directory"
    ),
) -> None:
    """Show migration history."""
    from alembic import command

    from agent_gateway.persistence.migrations.runner import get_config_for_url

    url = _normalize_url(_get_db_url(workspace))
    cfg = get_config_for_url(url)
    command.history(cfg, verbose=True)
