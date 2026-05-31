"""add tool artifacts

Revision ID: 0d4f7b9c2a11
Revises: f4a9c8d2b671
Create Date: 2026-05-31 16:45:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0d4f7b9c2a11"
down_revision = "f4a9c8d2b671"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade():
    if _table_exists("tool_artifacts"):
        return
    op.create_table(
        "tool_artifacts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("tool_call_id", sa.String(), nullable=True),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False, server_default="application/json"),
        sa.Column("preview", sa.Text(), nullable=True),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("artifact_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_artifacts_session_id", "tool_artifacts", ["session_id"])
    op.create_index("ix_tool_artifacts_message_id", "tool_artifacts", ["message_id"])
    op.create_index("ix_tool_artifacts_user_id", "tool_artifacts", ["user_id"])
    op.create_index("ix_tool_artifacts_agent_id", "tool_artifacts", ["agent_id"])
    op.create_index("ix_tool_artifacts_request_id", "tool_artifacts", ["request_id"])
    op.create_index("ix_tool_artifacts_tool_call_id", "tool_artifacts", ["tool_call_id"])
    op.create_index("ix_tool_artifacts_tool_name", "tool_artifacts", ["tool_name"])
    op.create_index("ix_tool_artifacts_created_at", "tool_artifacts", ["created_at"])


def downgrade():
    if not _table_exists("tool_artifacts"):
        return
    op.drop_index("ix_tool_artifacts_created_at", table_name="tool_artifacts")
    op.drop_index("ix_tool_artifacts_tool_name", table_name="tool_artifacts")
    op.drop_index("ix_tool_artifacts_tool_call_id", table_name="tool_artifacts")
    op.drop_index("ix_tool_artifacts_request_id", table_name="tool_artifacts")
    op.drop_index("ix_tool_artifacts_agent_id", table_name="tool_artifacts")
    op.drop_index("ix_tool_artifacts_user_id", table_name="tool_artifacts")
    op.drop_index("ix_tool_artifacts_message_id", table_name="tool_artifacts")
    op.drop_index("ix_tool_artifacts_session_id", table_name="tool_artifacts")
    op.drop_table("tool_artifacts")
