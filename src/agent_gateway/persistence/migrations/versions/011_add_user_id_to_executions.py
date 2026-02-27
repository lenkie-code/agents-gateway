"""Add user_id column to executions table.

Revision ID: 011
Revises: 010
Create Date: 2026-02-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "executions",
        sa.Column("user_id", sa.String, nullable=True),
    )
    op.create_index("ix_executions_user_id", "executions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_executions_user_id", table_name="executions")
    op.drop_column("executions", "user_id")
