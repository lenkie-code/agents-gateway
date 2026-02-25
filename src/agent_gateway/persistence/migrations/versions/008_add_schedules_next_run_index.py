"""Add missing ix_schedules_next_run partial index.

Revision ID: 008
Revises: 007
Create Date: 2026-02-25
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Partial index — only meaningful on PostgreSQL.
    # SQLite ignores the WHERE clause but still creates the index.
    op.create_index(
        "ix_schedules_next_run",
        "schedules",
        ["next_run_at"],
        postgresql_where=text("enabled = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_schedules_next_run", table_name="schedules")
