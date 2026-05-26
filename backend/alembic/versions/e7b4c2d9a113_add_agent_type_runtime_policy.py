"""add agent type and runtime policy

Revision ID: e7b4c2d9a113
Revises: c9f3a7e2d614
Create Date: 2026-05-06 10:30:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e7b4c2d9a113"
down_revision = "c9f3a7e2d614"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def upgrade():
    if not _column_exists("agent_profiles", "agent_type"):
        op.add_column(
            "agent_profiles",
            sa.Column("agent_type", sa.String(), nullable=False, server_default="general"),
        )
    if not _column_exists("agent_profiles", "runtime_policy"):
        op.add_column(
            "agent_profiles",
            sa.Column(
                "runtime_policy",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )


def downgrade():
    if _column_exists("agent_profiles", "runtime_policy"):
        op.drop_column("agent_profiles", "runtime_policy")
    if _column_exists("agent_profiles", "agent_type"):
        op.drop_column("agent_profiles", "agent_type")
