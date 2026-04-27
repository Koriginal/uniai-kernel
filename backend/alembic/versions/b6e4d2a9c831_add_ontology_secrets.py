"""add ontology secrets

Revision ID: b6e4d2a9c831
Revises: 9b2c7d8e4f01
Create Date: 2026-04-27 14:20:00

"""
from alembic import op
import sqlalchemy as sa


revision = "b6e4d2a9c831"
down_revision = "9b2c7d8e4f01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ontology_secrets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("space_id", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["space_id"], ["ontology_spaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("space_id", "scope", "name", name="uix_ontology_secret_space_scope_name"),
    )
    op.create_index(op.f("ix_ontology_secrets_space_id"), "ontology_secrets", ["space_id"], unique=False)
    op.create_index(op.f("ix_ontology_secrets_scope"), "ontology_secrets", ["scope"], unique=False)
    op.create_index(op.f("ix_ontology_secrets_created_by"), "ontology_secrets", ["created_by"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_ontology_secrets_created_by"), table_name="ontology_secrets")
    op.drop_index(op.f("ix_ontology_secrets_scope"), table_name="ontology_secrets")
    op.drop_index(op.f("ix_ontology_secrets_space_id"), table_name="ontology_secrets")
    op.drop_table("ontology_secrets")
