"""add ontology data sources

Revision ID: 9b2c7d8e4f01
Revises: f0a1b2c3d4e5
Create Date: 2026-04-27 10:40:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9b2c7d8e4f01"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ontology_data_sources",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("space_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("protocol", sa.String(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("secret_ref", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("last_test_status", sa.String(), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind in ('database','api','protocol','file','stream')", name="ck_ontology_data_sources_kind"),
        sa.CheckConstraint("status in ('draft','active','disabled')", name="ck_ontology_data_sources_status"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["space_id"], ["ontology_spaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("space_id", "name", name="uix_ontology_data_source_space_name"),
    )
    op.create_index(op.f("ix_ontology_data_sources_space_id"), "ontology_data_sources", ["space_id"], unique=False)
    op.create_index(op.f("ix_ontology_data_sources_kind"), "ontology_data_sources", ["kind"], unique=False)
    op.create_index(op.f("ix_ontology_data_sources_protocol"), "ontology_data_sources", ["protocol"], unique=False)
    op.create_index(op.f("ix_ontology_data_sources_status"), "ontology_data_sources", ["status"], unique=False)
    op.create_index(op.f("ix_ontology_data_sources_created_by"), "ontology_data_sources", ["created_by"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_ontology_data_sources_created_by"), table_name="ontology_data_sources")
    op.drop_index(op.f("ix_ontology_data_sources_status"), table_name="ontology_data_sources")
    op.drop_index(op.f("ix_ontology_data_sources_protocol"), table_name="ontology_data_sources")
    op.drop_index(op.f("ix_ontology_data_sources_kind"), table_name="ontology_data_sources")
    op.drop_index(op.f("ix_ontology_data_sources_space_id"), table_name="ontology_data_sources")
    op.drop_table("ontology_data_sources")
