"""Add source column to schedules table.

Revision ID: 010
Revises: 009
Create Date: 2026-02-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "schedules",
        sa.Column("source", sa.String, nullable=False, server_default="workspace"),
    )


def downgrade() -> None:
    op.drop_column("schedules", "source")
