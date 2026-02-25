"""Add notification_log table for delivery tracking.

Revision ID: 006
Revises: 005
Create Date: 2026-02-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("execution_id", sa.String, nullable=False),
        sa.Column("agent_id", sa.String, nullable=False),
        sa.Column("event_type", sa.String, nullable=False),
        sa.Column("channel", sa.String, nullable=False),
        sa.Column("target", sa.String, nullable=False, server_default=""),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notification_log_execution_id", "notification_log", ["execution_id"])
    op.create_index("ix_notification_log_agent_id", "notification_log", ["agent_id"])
    op.create_index("ix_notification_log_status", "notification_log", ["status"])


def downgrade() -> None:
    op.drop_index("ix_notification_log_status", table_name="notification_log")
    op.drop_index("ix_notification_log_agent_id", table_name="notification_log")
    op.drop_index("ix_notification_log_execution_id", table_name="notification_log")
    op.drop_table("notification_log")
