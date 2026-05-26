"""add ontology instance graphs

Revision ID: c9f3a7e2d614
Revises: b6e4d2a9c831
Create Date: 2026-04-28 11:40:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c9f3a7e2d614"
down_revision = "b6e4d2a9c831"
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
    if not _table_exists("ontology_instance_graphs"):
        op.create_table(
            "ontology_instance_graphs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("space_id", sa.String(), nullable=False),
            sa.Column("schema_version", sa.String(), nullable=True),
            sa.Column("mapping_version", sa.String(), nullable=True),
            sa.Column("decision_id", sa.String(), nullable=True),
            sa.Column("source", sa.String(), nullable=False, server_default="manual"),
            sa.Column("session_id", sa.String(), nullable=True),
            sa.Column("request_id", sa.String(), nullable=True),
            sa.Column("entity_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("relation_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("graph_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("trace", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["decision_id"], ["ontology_decisions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["space_id"], ["ontology_spaces.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_ontology_instance_graphs_space_id", "ontology_instance_graphs", ["space_id"])
    _create_index_if_missing("ix_ontology_instance_graphs_schema_version", "ontology_instance_graphs", ["schema_version"])
    _create_index_if_missing("ix_ontology_instance_graphs_mapping_version", "ontology_instance_graphs", ["mapping_version"])
    _create_index_if_missing("ix_ontology_instance_graphs_decision_id", "ontology_instance_graphs", ["decision_id"])
    _create_index_if_missing("ix_ontology_instance_graphs_source", "ontology_instance_graphs", ["source"])
    _create_index_if_missing("ix_ontology_instance_graphs_session_id", "ontology_instance_graphs", ["session_id"])
    _create_index_if_missing("ix_ontology_instance_graphs_request_id", "ontology_instance_graphs", ["request_id"])
    _create_index_if_missing("ix_ontology_instance_graphs_created_by", "ontology_instance_graphs", ["created_by"])
    _create_index_if_missing("ix_ontology_instance_graphs_space_created", "ontology_instance_graphs", ["space_id", "created_at"])
    _create_index_if_missing("ix_ontology_instance_graphs_space_source", "ontology_instance_graphs", ["space_id", "source"])


def downgrade():
    _drop_index_if_exists("ix_ontology_instance_graphs_space_source", "ontology_instance_graphs")
    _drop_index_if_exists("ix_ontology_instance_graphs_space_created", "ontology_instance_graphs")
    _drop_index_if_exists("ix_ontology_instance_graphs_created_by", "ontology_instance_graphs")
    _drop_index_if_exists("ix_ontology_instance_graphs_request_id", "ontology_instance_graphs")
    _drop_index_if_exists("ix_ontology_instance_graphs_session_id", "ontology_instance_graphs")
    _drop_index_if_exists("ix_ontology_instance_graphs_source", "ontology_instance_graphs")
    _drop_index_if_exists("ix_ontology_instance_graphs_decision_id", "ontology_instance_graphs")
    _drop_index_if_exists("ix_ontology_instance_graphs_mapping_version", "ontology_instance_graphs")
    _drop_index_if_exists("ix_ontology_instance_graphs_schema_version", "ontology_instance_graphs")
    _drop_index_if_exists("ix_ontology_instance_graphs_space_id", "ontology_instance_graphs")
    if _table_exists("ontology_instance_graphs"):
        op.drop_table("ontology_instance_graphs")
