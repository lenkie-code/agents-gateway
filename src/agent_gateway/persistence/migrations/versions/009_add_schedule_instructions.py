"""Add instructions column to schedules and user_schedules.

Revision ID: 009
Revises: 008
Create Date: 2026-02-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("schedules", sa.Column("instructions", sa.Text, nullable=True))
    op.add_column("user_schedules", sa.Column("instructions", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("user_schedules", "instructions")
    op.drop_column("schedules", "instructions")
