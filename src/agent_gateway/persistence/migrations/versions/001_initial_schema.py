"""Initial schema — baseline of all existing tables.

Revision ID: 001
Revises: None
Create Date: 2026-02-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "executions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("agent_id", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="queued"),
        sa.Column("message", sa.Text, nullable=False, server_default=""),
        sa.Column("input", sa.JSON),
        sa.Column("options", sa.JSON),
        sa.Column("result", sa.JSON),
        sa.Column("error", sa.Text),
        sa.Column("usage", sa.JSON),
        sa.Column("session_id", sa.String, nullable=True),
        sa.Column("schedule_id", sa.String, nullable=True),
        sa.Column("schedule_name", sa.String, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_executions_agent_id", "executions", ["agent_id"])
    op.create_index("ix_executions_session_id", "executions", ["session_id"])
    op.create_index("ix_executions_schedule_id", "executions", ["schedule_id"])

    op.create_table(
        "execution_steps",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "execution_id",
            sa.String,
            sa.ForeignKey("executions.id"),
            nullable=False,
        ),
        sa.Column("step_type", sa.String, nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("data", sa.JSON),
        sa.Column("duration_ms", sa.Integer, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_execution_steps_execution_id", "execution_steps", ["execution_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String, nullable=False),
        sa.Column("actor", sa.String),
        sa.Column("resource_type", sa.String),
        sa.Column("resource_id", sa.String),
        sa.Column("metadata", sa.JSON),
        sa.Column("ip_address", sa.String),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_audit_log_event_type", "audit_log", ["event_type"])

    op.create_table(
        "schedules",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("agent_id", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("cron_expr", sa.String, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("input", sa.JSON),
        sa.Column("enabled", sa.Boolean, server_default="1"),
        sa.Column("timezone", sa.String, server_default="UTC"),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_schedules_agent_id", "schedules", ["agent_id"])

    op.create_table(
        "users",
        sa.Column("user_id", sa.String, primary_key=True),
        sa.Column("display_name", sa.String, nullable=True),
        sa.Column("email", sa.String, nullable=True),
        sa.Column("metadata_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "conversations",
        sa.Column("conversation_id", sa.String, primary_key=True),
        sa.Column("agent_id", sa.String, nullable=False),
        sa.Column("user_id", sa.String, nullable=True),
        sa.Column("title", sa.String, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("message_count", sa.Integer, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_conversations_user_agent", "conversations", ["user_id", "agent_id"])
    op.create_index("ix_conversations_user", "conversations", ["user_id"])

    op.create_table(
        "conversation_messages",
        sa.Column("message_id", sa.String, primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String,
            sa.ForeignKey("conversations.conversation_id"),
            nullable=False,
        ),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata_json", sa.JSON, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_conv_messages_conv_id", "conversation_messages", ["conversation_id"])

    op.create_table(
        "memories",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("agent_id", sa.String, nullable=False),
        sa.Column("user_id", sa.String, nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("memory_type", sa.String, nullable=False, server_default="semantic"),
        sa.Column("source", sa.String, nullable=False, server_default="manual"),
        sa.Column("importance", sa.Float, server_default="0.5"),
        sa.Column("access_count", sa.Integer, server_default="0"),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_memories_agent_user", "memories", ["agent_id", "user_id"])
    op.create_index("ix_memories_agent_id", "memories", ["agent_id"])


def downgrade() -> None:
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
    op.drop_table("memories")
    op.drop_table("execution_steps")
    op.drop_table("executions")
    op.drop_table("audit_log")
    op.drop_table("schedules")
    op.drop_table("users")
