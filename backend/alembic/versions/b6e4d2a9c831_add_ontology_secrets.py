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


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], unique: bool = False) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _table_exists(table_name) and _index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade():
    if not _table_exists("ontology_secrets"):
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
    _create_index_if_missing("ix_ontology_secrets_space_id", "ontology_secrets", ["space_id"])
    _create_index_if_missing("ix_ontology_secrets_scope", "ontology_secrets", ["scope"])
    _create_index_if_missing("ix_ontology_secrets_created_by", "ontology_secrets", ["created_by"])


def downgrade():
    _drop_index_if_exists("ix_ontology_secrets_created_by", "ontology_secrets")
    _drop_index_if_exists("ix_ontology_secrets_scope", "ontology_secrets")
    _drop_index_if_exists("ix_ontology_secrets_space_id", "ontology_secrets")
    if _table_exists("ontology_secrets"):
        op.drop_table("ontology_secrets")
