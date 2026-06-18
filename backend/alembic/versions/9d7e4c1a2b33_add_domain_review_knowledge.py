"""add domain review knowledge

Revision ID: 9d7e4c1a2b33
Revises: 6f2b8d4c1a90
Create Date: 2026-06-03 00:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9d7e4c1a2b33"
down_revision = "6f2b8d4c1a90"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {item["name"] for item in inspector.get_columns(table_name)}


def upgrade():
    if not _table_exists("policy_documents"):
        op.create_table(
            "policy_documents",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("space_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("source_document_id", sa.String(), nullable=True),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("business_domain", sa.String(), nullable=True),
            sa.Column("document_type", sa.String(), nullable=False),
            sa.Column("version", sa.String(), nullable=False, server_default="1"),
            sa.Column("raw_text_hash", sa.String(), nullable=False),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["space_id"], ["ontology_spaces.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_document_id"], ["rule_source_documents.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("space_id", "source_document_id", "version", name="uix_policy_documents_source_version"),
            sa.CheckConstraint("document_type in ('contract_rule','tender_rule','policy_doc','review_manual','custom')", name="ck_policy_documents_document_type"),
            sa.CheckConstraint("status in ('draft','segmented','norms_extracted','reviewed','archived')", name="ck_policy_documents_status"),
        )
        op.create_index("ix_policy_documents_space_id", "policy_documents", ["space_id"])
        op.create_index("ix_policy_documents_user_id", "policy_documents", ["user_id"])
        op.create_index("ix_policy_documents_source_document_id", "policy_documents", ["source_document_id"])
        op.create_index("ix_policy_documents_business_domain", "policy_documents", ["business_domain"])
        op.create_index("ix_policy_documents_document_type", "policy_documents", ["document_type"])
        op.create_index("ix_policy_documents_status", "policy_documents", ["status"])
        op.create_index("ix_policy_documents_space_type", "policy_documents", ["space_id", "document_type"])

    if not _table_exists("policy_articles"):
        op.create_table(
            "policy_articles",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("space_id", sa.String(), nullable=False),
            sa.Column("policy_document_id", sa.String(), nullable=False),
            sa.Column("article_no", sa.String(), nullable=False),
            sa.Column("chapter_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("paragraph_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("locator", sa.String(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("quote", sa.Text(), nullable=False),
            sa.Column("text_hash", sa.String(), nullable=False),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["policy_document_id"], ["policy_documents.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["space_id"], ["ontology_spaces.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("policy_document_id", "locator", name="uix_policy_articles_document_locator"),
        )
        op.create_index("ix_policy_articles_space_id", "policy_articles", ["space_id"])
        op.create_index("ix_policy_articles_policy_document_id", "policy_articles", ["policy_document_id"])
        op.create_index("ix_policy_articles_space_document", "policy_articles", ["space_id", "policy_document_id"])

    if not _table_exists("norm_clauses"):
        op.create_table(
            "norm_clauses",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("space_id", sa.String(), nullable=False),
            sa.Column("policy_document_id", sa.String(), nullable=False),
            sa.Column("policy_article_id", sa.String(), nullable=False),
            sa.Column("norm_code", sa.String(), nullable=False),
            sa.Column("norm_type", sa.String(), nullable=False),
            sa.Column("subject", sa.String(), nullable=True),
            sa.Column("action", sa.String(), nullable=True),
            sa.Column("object", sa.String(), nullable=True),
            sa.Column("condition_text", sa.Text(), nullable=True),
            sa.Column("exception_text", sa.Text(), nullable=True),
            sa.Column("consequence_text", sa.Text(), nullable=True),
            sa.Column("evidence_required", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("domain_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("scenario_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("confidence", sa.String(), nullable=False, server_default="medium"),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.Column("reviewed_by", sa.String(), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["policy_article_id"], ["policy_articles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["policy_document_id"], ["policy_documents.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["space_id"], ["ontology_spaces.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("space_id", "norm_code", name="uix_norm_clauses_space_code"),
            sa.CheckConstraint("norm_type in ('obligation','prohibition','permission','exception','approval_required','evidence_required','liability','standard','scoring')", name="ck_norm_clauses_norm_type"),
            sa.CheckConstraint("confidence in ('low','medium','high')", name="ck_norm_clauses_confidence"),
            sa.CheckConstraint("status in ('draft','approved','rejected','released','deprecated')", name="ck_norm_clauses_status"),
        )
        for name, cols in {
            "ix_norm_clauses_space_id": ["space_id"],
            "ix_norm_clauses_policy_document_id": ["policy_document_id"],
            "ix_norm_clauses_policy_article_id": ["policy_article_id"],
            "ix_norm_clauses_norm_type": ["norm_type"],
            "ix_norm_clauses_status": ["status"],
            "ix_norm_clauses_created_by": ["created_by"],
            "ix_norm_clauses_reviewed_by": ["reviewed_by"],
            "ix_norm_clauses_space_status": ["space_id", "status"],
        }.items():
            op.create_index(name, "norm_clauses", cols)

    if not _table_exists("review_checks"):
        op.create_table(
            "review_checks",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("space_id", sa.String(), nullable=False),
            sa.Column("check_code", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("scenario_type", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("norm_clause_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("input_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
            sa.Column("evidence_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
            sa.Column("check_type", sa.String(), nullable=False, server_default="semantic"),
            sa.Column("severity", sa.String(), nullable=False, server_default="medium"),
            sa.Column("fail_template", sa.Text(), nullable=True),
            sa.Column("pass_template", sa.Text(), nullable=True),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.Column("reviewed_by", sa.String(), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["space_id"], ["ontology_spaces.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("space_id", "check_code", name="uix_review_checks_space_code"),
            sa.CheckConstraint("scenario_type in ('contract_review','tender_review','custom')", name="ck_review_checks_scenario_type"),
            sa.CheckConstraint("check_type in ('deterministic','semantic','manual')", name="ck_review_checks_check_type"),
            sa.CheckConstraint("severity in ('low','medium','high','critical')", name="ck_review_checks_severity"),
            sa.CheckConstraint("status in ('draft','approved','rejected','released','deprecated')", name="ck_review_checks_status"),
        )
        for name, cols in {
            "ix_review_checks_space_id": ["space_id"],
            "ix_review_checks_scenario_type": ["scenario_type"],
            "ix_review_checks_severity": ["severity"],
            "ix_review_checks_status": ["status"],
            "ix_review_checks_created_by": ["created_by"],
            "ix_review_checks_reviewed_by": ["reviewed_by"],
            "ix_review_checks_space_scenario": ["space_id", "scenario_type"],
        }.items():
            op.create_index(name, "review_checks", cols)

    if not _table_exists("review_packs"):
        op.create_table(
            "review_packs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("space_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("business_domain", sa.String(), nullable=True),
            sa.Column("scenario_type", sa.String(), nullable=False),
            sa.Column("version", sa.String(), nullable=False),
            sa.Column("policy_document_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("norm_clause_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("review_check_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("created_by", sa.String(), nullable=False),
            sa.Column("released_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["released_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["space_id"], ["ontology_spaces.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("space_id", "name", "version", name="uix_review_packs_space_name_version"),
            sa.CheckConstraint("scenario_type in ('contract_review','tender_review','custom')", name="ck_review_packs_scenario_type"),
            sa.CheckConstraint("status in ('draft','released','archived')", name="ck_review_packs_status"),
        )
        for name, cols in {
            "ix_review_packs_space_id": ["space_id"],
            "ix_review_packs_business_domain": ["business_domain"],
            "ix_review_packs_scenario_type": ["scenario_type"],
            "ix_review_packs_status": ["status"],
            "ix_review_packs_created_by": ["created_by"],
            "ix_review_packs_released_by": ["released_by"],
            "ix_review_packs_space_status": ["space_id", "status"],
        }.items():
            op.create_index(name, "review_packs", cols)

    if not _table_exists("review_runs"):
        op.create_table(
            "review_runs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("application_id", sa.String(), nullable=True),
            sa.Column("review_pack_id", sa.String(), nullable=True),
            sa.Column("target_document_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("target_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
            sa.Column("extracted_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
            sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
            sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(), nullable=False, server_default="completed"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["application_id"], ["agent_applications.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["review_pack_id"], ["review_packs.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint("status in ('completed','failed')", name="ck_review_runs_status"),
        )
        for name, cols in {
            "ix_review_runs_user_id": ["user_id"],
            "ix_review_runs_application_id": ["application_id"],
            "ix_review_runs_review_pack_id": ["review_pack_id"],
            "ix_review_runs_status": ["status"],
            "ix_review_runs_user_created": ["user_id", "created_at"],
        }.items():
            op.create_index(name, "review_runs", cols)

    if _table_exists("agent_applications"):
        if not _column_exists("agent_applications", "review_pack_id"):
            op.add_column("agent_applications", sa.Column("review_pack_id", sa.String(), nullable=True))
            op.create_index("ix_agent_applications_review_pack_id", "agent_applications", ["review_pack_id"])
            op.create_foreign_key("fk_agent_applications_review_pack_id", "agent_applications", "review_packs", ["review_pack_id"], ["id"], ondelete="SET NULL")
        if not _column_exists("agent_applications", "review_pack_version"):
            op.add_column("agent_applications", sa.Column("review_pack_version", sa.String(), nullable=True))


def downgrade():
    if _column_exists("agent_applications", "review_pack_id"):
        op.drop_constraint("fk_agent_applications_review_pack_id", "agent_applications", type_="foreignkey")
        op.drop_index("ix_agent_applications_review_pack_id", table_name="agent_applications")
        op.drop_column("agent_applications", "review_pack_id")
    if _column_exists("agent_applications", "review_pack_version"):
        op.drop_column("agent_applications", "review_pack_version")
    for table in ["review_runs", "review_packs", "review_checks", "norm_clauses", "policy_articles", "policy_documents"]:
        if _table_exists(table):
            op.drop_table(table)
