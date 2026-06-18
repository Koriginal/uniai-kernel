"""add rule asset pipeline

Revision ID: 6f2b8d4c1a90
Revises: 5a1d9c0e7b62
Create Date: 2026-06-02 00:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "6f2b8d4c1a90"
down_revision = "5a1d9c0e7b62"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade():
    if not _table_exists("rule_source_documents"):
        op.create_table(
            "rule_source_documents",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("space_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("source_type", sa.String(), nullable=False),
            sa.Column("file_name", sa.String(), nullable=True),
            sa.Column("content_type", sa.String(), nullable=True),
            sa.Column("content_hash", sa.String(), nullable=False),
            sa.Column("raw_text", sa.Text(), nullable=True),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(), nullable=False, server_default="uploaded"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["space_id"], ["ontology_spaces.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("space_id", "content_hash", name="uix_rule_source_space_hash"),
            sa.CheckConstraint(
                "source_type in ('policy_doc','contract_template','review_manual','regulation','historical_case','database_schema','api_schema','custom_note')",
                name="ck_rule_source_documents_source_type",
            ),
            sa.CheckConstraint(
                "status in ('uploaded','parsed','parse_failed','reviewed','archived')",
                name="ck_rule_source_documents_status",
            ),
        )
        op.create_index("ix_rule_source_documents_space_id", "rule_source_documents", ["space_id"])
        op.create_index("ix_rule_source_documents_user_id", "rule_source_documents", ["user_id"])
        op.create_index("ix_rule_source_documents_source_type", "rule_source_documents", ["source_type"])
        op.create_index("ix_rule_source_documents_status", "rule_source_documents", ["status"])
        op.create_index("ix_rule_source_documents_space_created", "rule_source_documents", ["space_id", "created_at"])

    if not _table_exists("rule_entries"):
        op.create_table(
            "rule_entries",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("space_id", sa.String(), nullable=False),
            sa.Column("source_document_id", sa.String(), nullable=True),
            sa.Column("rule_code", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("target_entity_type", sa.String(), nullable=True),
            sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("severity", sa.String(), nullable=False, server_default="medium"),
            sa.Column("action", sa.String(), nullable=False, server_default="flag"),
            sa.Column("evidence_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("test_cases", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("version", sa.String(), nullable=False, server_default="1"),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.Column("reviewed_by", sa.String(), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["source_document_id"], ["rule_source_documents.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["space_id"], ["ontology_spaces.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("space_id", "rule_code", name="uix_rule_entries_space_rule_code"),
            sa.CheckConstraint("severity in ('low','medium','high','critical')", name="ck_rule_entries_severity"),
            sa.CheckConstraint("action in ('flag','block','recommend')", name="ck_rule_entries_action"),
            sa.CheckConstraint(
                "status in ('draft','reviewing','approved','rejected','packaged','released','deprecated')",
                name="ck_rule_entries_status",
            ),
        )
        op.create_index("ix_rule_entries_space_id", "rule_entries", ["space_id"])
        op.create_index("ix_rule_entries_source_document_id", "rule_entries", ["source_document_id"])
        op.create_index("ix_rule_entries_severity", "rule_entries", ["severity"])
        op.create_index("ix_rule_entries_action", "rule_entries", ["action"])
        op.create_index("ix_rule_entries_status", "rule_entries", ["status"])
        op.create_index("ix_rule_entries_created_by", "rule_entries", ["created_by"])
        op.create_index("ix_rule_entries_reviewed_by", "rule_entries", ["reviewed_by"])
        op.create_index("ix_rule_entries_space_status", "rule_entries", ["space_id", "status"])
        op.create_index("ix_rule_entries_space_updated", "rule_entries", ["space_id", "updated_at"])

    if not _table_exists("ontology_terms"):
        op.create_table(
            "ontology_terms",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("space_id", sa.String(), nullable=False),
            sa.Column("source_document_id", sa.String(), nullable=True),
            sa.Column("term_code", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("entity_type", sa.String(), nullable=True),
            sa.Column("data_type", sa.String(), nullable=True),
            sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("enum_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("relation_target_type", sa.String(), nullable=True),
            sa.Column("relation_cardinality", sa.String(), nullable=True),
            sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("evidence_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("version", sa.String(), nullable=False, server_default="1"),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.Column("reviewed_by", sa.String(), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["source_document_id"], ["rule_source_documents.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["space_id"], ["ontology_spaces.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("space_id", "term_code", name="uix_ontology_terms_space_term_code"),
            sa.CheckConstraint("kind in ('entity','attribute','relation','enum','taxonomy','vocabulary')", name="ck_ontology_terms_kind"),
            sa.CheckConstraint("status in ('draft','reviewing','approved','rejected','packaged','released','deprecated')", name="ck_ontology_terms_status"),
            sa.CheckConstraint("data_type is null or data_type in ('string','number','integer','boolean','array','object')", name="ck_ontology_terms_data_type"),
            sa.CheckConstraint("relation_cardinality is null or relation_cardinality in ('one','many')", name="ck_ontology_terms_relation_cardinality"),
        )
        op.create_index("ix_ontology_terms_space_id", "ontology_terms", ["space_id"])
        op.create_index("ix_ontology_terms_source_document_id", "ontology_terms", ["source_document_id"])
        op.create_index("ix_ontology_terms_kind", "ontology_terms", ["kind"])
        op.create_index("ix_ontology_terms_entity_type", "ontology_terms", ["entity_type"])
        op.create_index("ix_ontology_terms_status", "ontology_terms", ["status"])
        op.create_index("ix_ontology_terms_created_by", "ontology_terms", ["created_by"])
        op.create_index("ix_ontology_terms_reviewed_by", "ontology_terms", ["reviewed_by"])
        op.create_index("ix_ontology_terms_space_kind", "ontology_terms", ["space_id", "kind"])
        op.create_index("ix_ontology_terms_space_status", "ontology_terms", ["space_id", "status"])


def downgrade():
    if _table_exists("ontology_terms"):
        op.drop_index("ix_ontology_terms_space_status", table_name="ontology_terms")
        op.drop_index("ix_ontology_terms_space_kind", table_name="ontology_terms")
        op.drop_index("ix_ontology_terms_reviewed_by", table_name="ontology_terms")
        op.drop_index("ix_ontology_terms_created_by", table_name="ontology_terms")
        op.drop_index("ix_ontology_terms_status", table_name="ontology_terms")
        op.drop_index("ix_ontology_terms_entity_type", table_name="ontology_terms")
        op.drop_index("ix_ontology_terms_kind", table_name="ontology_terms")
        op.drop_index("ix_ontology_terms_source_document_id", table_name="ontology_terms")
        op.drop_index("ix_ontology_terms_space_id", table_name="ontology_terms")
        op.drop_table("ontology_terms")
    if _table_exists("rule_entries"):
        op.drop_index("ix_rule_entries_space_updated", table_name="rule_entries")
        op.drop_index("ix_rule_entries_space_status", table_name="rule_entries")
        op.drop_index("ix_rule_entries_reviewed_by", table_name="rule_entries")
        op.drop_index("ix_rule_entries_created_by", table_name="rule_entries")
        op.drop_index("ix_rule_entries_status", table_name="rule_entries")
        op.drop_index("ix_rule_entries_action", table_name="rule_entries")
        op.drop_index("ix_rule_entries_severity", table_name="rule_entries")
        op.drop_index("ix_rule_entries_source_document_id", table_name="rule_entries")
        op.drop_index("ix_rule_entries_space_id", table_name="rule_entries")
        op.drop_table("rule_entries")
    if _table_exists("rule_source_documents"):
        op.drop_index("ix_rule_source_documents_space_created", table_name="rule_source_documents")
        op.drop_index("ix_rule_source_documents_status", table_name="rule_source_documents")
        op.drop_index("ix_rule_source_documents_source_type", table_name="rule_source_documents")
        op.drop_index("ix_rule_source_documents_user_id", table_name="rule_source_documents")
        op.drop_index("ix_rule_source_documents_space_id", table_name="rule_source_documents")
        op.drop_table("rule_source_documents")
