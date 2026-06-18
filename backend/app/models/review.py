from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.db import Base


class PolicyDocumentModel(Base):
    __tablename__ = "policy_documents"

    id = Column(String, primary_key=True)
    space_id = Column(String, ForeignKey("ontology_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    source_document_id = Column(String, ForeignKey("rule_source_documents.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String, nullable=False)
    business_domain = Column(String, nullable=True, index=True)
    document_type = Column(String, nullable=False, index=True)
    version = Column(String, nullable=False, default="1")
    raw_text_hash = Column(String, nullable=False)
    metadata_json = Column(JSONB, nullable=False, default={})
    status = Column(String, nullable=False, default="draft", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("space_id", "source_document_id", "version", name="uix_policy_documents_source_version"),
        CheckConstraint("document_type in ('contract_rule','tender_rule','policy_doc','review_manual','custom')", name="ck_policy_documents_document_type"),
        CheckConstraint("status in ('draft','segmented','norms_extracted','reviewed','archived')", name="ck_policy_documents_status"),
        Index("ix_policy_documents_space_type", "space_id", "document_type"),
    )


class PolicyArticleModel(Base):
    __tablename__ = "policy_articles"

    id = Column(String, primary_key=True)
    space_id = Column(String, ForeignKey("ontology_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_document_id = Column(String, ForeignKey("policy_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    article_no = Column(String, nullable=False)
    chapter_path = Column(JSONB, nullable=False, default=[])
    paragraph_path = Column(JSONB, nullable=False, default=[])
    locator = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    quote = Column(Text, nullable=False)
    text_hash = Column(String, nullable=False)
    metadata_json = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("policy_document_id", "locator", name="uix_policy_articles_document_locator"),
        Index("ix_policy_articles_space_document", "space_id", "policy_document_id"),
    )


class NormClauseModel(Base):
    __tablename__ = "norm_clauses"

    id = Column(String, primary_key=True)
    space_id = Column(String, ForeignKey("ontology_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_document_id = Column(String, ForeignKey("policy_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_article_id = Column(String, ForeignKey("policy_articles.id", ondelete="CASCADE"), nullable=False, index=True)
    norm_code = Column(String, nullable=False)
    norm_type = Column(String, nullable=False, index=True)
    subject = Column(String, nullable=True)
    action = Column(String, nullable=True)
    object = Column(String, nullable=True)
    condition_text = Column(Text, nullable=True)
    exception_text = Column(Text, nullable=True)
    consequence_text = Column(Text, nullable=True)
    evidence_required = Column(JSONB, nullable=False, default=[])
    domain_tags = Column(JSONB, nullable=False, default=[])
    scenario_tags = Column(JSONB, nullable=False, default=[])
    confidence = Column(String, nullable=False, default="medium")
    metadata_json = Column(JSONB, nullable=False, default={})
    status = Column(String, nullable=False, default="draft", index=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("space_id", "norm_code", name="uix_norm_clauses_space_code"),
        CheckConstraint("norm_type in ('obligation','prohibition','permission','exception','approval_required','evidence_required','liability','standard','scoring')", name="ck_norm_clauses_norm_type"),
        CheckConstraint("confidence in ('low','medium','high')", name="ck_norm_clauses_confidence"),
        CheckConstraint("status in ('draft','approved','rejected','released','deprecated')", name="ck_norm_clauses_status"),
        Index("ix_norm_clauses_space_status", "space_id", "status"),
    )


class ReviewCheckModel(Base):
    __tablename__ = "review_checks"

    id = Column(String, primary_key=True)
    space_id = Column(String, ForeignKey("ontology_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    check_code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    scenario_type = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    norm_clause_ids = Column(JSONB, nullable=False, default=[])
    input_schema = Column(JSONB, nullable=False, default={})
    evidence_schema = Column(JSONB, nullable=False, default={})
    check_type = Column(String, nullable=False, default="semantic")
    severity = Column(String, nullable=False, default="medium", index=True)
    fail_template = Column(Text, nullable=True)
    pass_template = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default={})
    status = Column(String, nullable=False, default="draft", index=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("space_id", "check_code", name="uix_review_checks_space_code"),
        CheckConstraint("scenario_type in ('contract_review','tender_review','custom')", name="ck_review_checks_scenario_type"),
        CheckConstraint("check_type in ('deterministic','semantic','manual')", name="ck_review_checks_check_type"),
        CheckConstraint("severity in ('low','medium','high','critical')", name="ck_review_checks_severity"),
        CheckConstraint("status in ('draft','approved','rejected','released','deprecated')", name="ck_review_checks_status"),
        Index("ix_review_checks_space_scenario", "space_id", "scenario_type"),
    )


class ReviewPackModel(Base):
    __tablename__ = "review_packs"

    id = Column(String, primary_key=True)
    space_id = Column(String, ForeignKey("ontology_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    business_domain = Column(String, nullable=True, index=True)
    scenario_type = Column(String, nullable=False, index=True)
    version = Column(String, nullable=False)
    policy_document_ids = Column(JSONB, nullable=False, default=[])
    norm_clause_ids = Column(JSONB, nullable=False, default=[])
    review_check_ids = Column(JSONB, nullable=False, default=[])
    metadata_json = Column(JSONB, nullable=False, default={})
    status = Column(String, nullable=False, default="draft", index=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    released_by = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    released_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("space_id", "name", "version", name="uix_review_packs_space_name_version"),
        CheckConstraint("scenario_type in ('contract_review','tender_review','custom')", name="ck_review_packs_scenario_type"),
        CheckConstraint("status in ('draft','released','archived')", name="ck_review_packs_status"),
        Index("ix_review_packs_space_status", "space_id", "status"),
    )


class ReviewRunModel(Base):
    __tablename__ = "review_runs"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    application_id = Column(String, ForeignKey("agent_applications.id", ondelete="SET NULL"), nullable=True, index=True)
    review_pack_id = Column(String, ForeignKey("review_packs.id", ondelete="SET NULL"), nullable=True, index=True)
    target_document_ids = Column(JSONB, nullable=False, default=[])
    target_snapshot = Column(JSONB, nullable=False, default={})
    extracted_facts = Column(JSONB, nullable=False, default={})
    findings = Column(JSONB, nullable=False, default=[])
    citations = Column(JSONB, nullable=False, default=[])
    summary = Column(JSONB, nullable=False, default={})
    status = Column(String, nullable=False, default="completed", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status in ('completed','failed')", name="ck_review_runs_status"),
        Index("ix_review_runs_user_created", "user_id", "created_at"),
    )
