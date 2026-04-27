"""add agent ontology config

Revision ID: f0a1b2c3d4e5
Revises: d8f1c4e2ab77
Create Date: 2026-04-24 10:30:00

"""
from alembic import op
import sqlalchemy as sa


revision = "f0a1b2c3d4e5"
down_revision = "d8f1c4e2ab77"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_profiles",
        sa.Column("ontology_config", sa.JSON(), nullable=True, server_default=sa.text("'{}'::json")),
    )


def downgrade():
    op.drop_column("agent_profiles", "ontology_config")
