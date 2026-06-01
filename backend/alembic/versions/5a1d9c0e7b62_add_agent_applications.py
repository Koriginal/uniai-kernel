"""add agent applications

Revision ID: 5a1d9c0e7b62
Revises: 0d4f7b9c2a11
Create Date: 2026-06-01 00:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "5a1d9c0e7b62"
down_revision = "0d4f7b9c2a11"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade():
    if _table_exists("agent_applications"):
        return
    op.create_table(
        "agent_applications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("business_domain", sa.String(), nullable=True),
        sa.Column("scenario_type", sa.String(), nullable=False, server_default="custom"),
        sa.Column("primary_agent_id", sa.String(), nullable=True),
        sa.Column("runtime_provider_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tool_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ontology_space_id", sa.String(), nullable=True),
        sa.Column("runtime_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("acceptance_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["primary_agent_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_applications_user_id", "agent_applications", ["user_id"])
    op.create_index("ix_agent_applications_primary_agent_id", "agent_applications", ["primary_agent_id"])
    op.create_index("ix_agent_applications_ontology_space_id", "agent_applications", ["ontology_space_id"])
    op.create_index("ix_agent_applications_status", "agent_applications", ["status"])


def downgrade():
    if not _table_exists("agent_applications"):
        return
    op.drop_index("ix_agent_applications_status", table_name="agent_applications")
    op.drop_index("ix_agent_applications_ontology_space_id", table_name="agent_applications")
    op.drop_index("ix_agent_applications_primary_agent_id", table_name="agent_applications")
    op.drop_index("ix_agent_applications_user_id", table_name="agent_applications")
    op.drop_table("agent_applications")
