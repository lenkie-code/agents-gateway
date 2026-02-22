"""Programmatic Alembic migration runner for agent-gateway."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from alembic import command
from alembic.config import Config

if TYPE_CHECKING:
    from sqlalchemy import Connection

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent


def _make_config(connection: Connection | None = None, url: str | None = None) -> Config:
    """Build an Alembic Config pointing at our migrations directory."""
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))

    if connection is not None:
        cfg.attributes["connection"] = connection
    elif url is not None:
        cfg.set_main_option("sqlalchemy.url", url)

    return cfg


def run_upgrade(connection: Connection, revision: str = "head") -> None:
    """Run Alembic upgrade using an existing connection (synchronous)."""
    cfg = _make_config(connection=connection)
    command.upgrade(cfg, revision)


def run_downgrade(connection: Connection, revision: str = "-1") -> None:
    """Run Alembic downgrade using an existing connection (synchronous)."""
    cfg = _make_config(connection=connection)
    command.downgrade(cfg, revision)


def get_current_revision(connection: Connection) -> str | None:
    """Get the current migration revision."""
    from alembic.runtime.migration import MigrationContext

    context = MigrationContext.configure(connection)
    return context.get_current_revision()


def get_config_for_url(url: str) -> Config:
    """Build an Alembic Config for CLI usage with a database URL."""
    return _make_config(url=url)
