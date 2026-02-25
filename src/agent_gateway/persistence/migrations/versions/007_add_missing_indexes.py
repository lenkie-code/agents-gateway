"""Add missing indexes on created_at and status columns.

Revision ID: 007
Revises: 006
Create Date: 2026-02-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_executions_created_at", "executions", ["created_at"])
    op.create_index("ix_executions_status", "executions", ["status"])
    op.create_index("ix_conversations_created_at", "conversations", ["created_at"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index("ix_conversations_created_at", table_name="conversations")
    op.drop_index("ix_executions_status", table_name="executions")
    op.drop_index("ix_executions_created_at", table_name="executions")
