from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.db import Base


class RuleSourceDocumentModel(Base):
    __tablename__ = "rule_source_documents"

    id = Column(String, primary_key=True)
    space_id = Column(String, ForeignKey("ontology_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    source_type = Column(String, nullable=False, index=True)
    file_name = Column(String, nullable=True)
    content_type = Column(String, nullable=True)
    content_hash = Column(String, nullable=False)
    raw_text = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default={})
    status = Column(String, nullable=False, default="uploaded", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("space_id", "content_hash", name="uix_rule_source_space_hash"),
        CheckConstraint(
            "source_type in ('policy_doc','contract_template','review_manual','regulation','historical_case','database_schema','api_schema','custom_note')",
            name="ck_rule_source_documents_source_type",
        ),
        CheckConstraint(
            "status in ('uploaded','parsed','parse_failed','reviewed','archived')",
            name="ck_rule_source_documents_status",
        ),
        Index("ix_rule_source_documents_space_created", "space_id", "created_at"),
    )


class RuleEntryModel(Base):
    __tablename__ = "rule_entries"

    id = Column(String, primary_key=True)
    space_id = Column(String, ForeignKey("ontology_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id = Column(String, ForeignKey("rule_source_documents.id", ondelete="SET NULL"), nullable=True, index=True)
    rule_code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    target_entity_type = Column(String, nullable=True)
    conditions = Column(JSONB, nullable=False, default=[])
    severity = Column(String, nullable=False, default="medium", index=True)
    action = Column(String, nullable=False, default="flag", index=True)
    evidence_refs = Column(JSONB, nullable=False, default=[])
    test_cases = Column(JSONB, nullable=False, default=[])
    tags = Column(JSONB, nullable=False, default=[])
    status = Column(String, nullable=False, default="draft", index=True)
    version = Column(String, nullable=False, default="1")
    created_by = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("space_id", "rule_code", name="uix_rule_entries_space_rule_code"),
        CheckConstraint("severity in ('low','medium','high','critical')", name="ck_rule_entries_severity"),
        CheckConstraint("action in ('flag','block','recommend')", name="ck_rule_entries_action"),
        CheckConstraint(
            "status in ('draft','reviewing','approved','rejected','packaged','released','deprecated')",
            name="ck_rule_entries_status",
        ),
        Index("ix_rule_entries_space_status", "space_id", "status"),
        Index("ix_rule_entries_space_updated", "space_id", "updated_at"),
    )


class OntologyTermModel(Base):
    __tablename__ = "ontology_terms"

    id = Column(String, primary_key=True)
    space_id = Column(String, ForeignKey("ontology_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id = Column(String, ForeignKey("rule_source_documents.id", ondelete="SET NULL"), nullable=True, index=True)
    term_code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    entity_type = Column(String, nullable=True, index=True)
    data_type = Column(String, nullable=True)
    required = Column(Boolean, nullable=False, default=False)
    enum_values = Column(JSONB, nullable=False, default=[])
    relation_target_type = Column(String, nullable=True)
    relation_cardinality = Column(String, nullable=True)
    aliases = Column(JSONB, nullable=False, default=[])
    evidence_refs = Column(JSONB, nullable=False, default=[])
    metadata_json = Column(JSONB, nullable=False, default={})
    status = Column(String, nullable=False, default="draft", index=True)
    version = Column(String, nullable=False, default="1")
    created_by = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("space_id", "term_code", name="uix_ontology_terms_space_term_code"),
        CheckConstraint("kind in ('entity','attribute','relation','enum','taxonomy','vocabulary')", name="ck_ontology_terms_kind"),
        CheckConstraint("status in ('draft','reviewing','approved','rejected','packaged','released','deprecated')", name="ck_ontology_terms_status"),
        CheckConstraint("data_type is null or data_type in ('string','number','integer','boolean','array','object')", name="ck_ontology_terms_data_type"),
        CheckConstraint("relation_cardinality is null or relation_cardinality in ('one','many')", name="ck_ontology_terms_relation_cardinality"),
        Index("ix_ontology_terms_space_kind", "space_id", "kind"),
        Index("ix_ontology_terms_space_status", "space_id", "status"),
    )
