from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index, text
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base


class OntologySpaceModel(Base):
    __tablename__ = "ontology_spaces"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    code = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    owner_user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    org_id = Column(String, ForeignKey("organizations.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("owner_user_id", "code", name="uix_ontology_space_owner_code"),
    )


class OntologyPackageModel(Base):
    __tablename__ = "ontology_packages"

    id = Column(String, primary_key=True)
    space_id = Column(String, ForeignKey("ontology_spaces.id"), nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)  # schema / mapping / rule
    version = Column(String, nullable=False)
    stage = Column(String, nullable=False, default="draft", index=True)
    is_active = Column(Boolean, nullable=False, default=False, index=True)

    payload = Column(JSONB, nullable=False, default={})
    notes = Column(Text, nullable=True)

    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("space_id", "kind", "version", name="uix_ontology_pkg_space_kind_version"),
        Index("ix_ontology_pkg_space_kind_stage", "space_id", "kind", "stage"),
        Index(
            "uix_ontology_pkg_single_active",
            "space_id",
            "kind",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
        CheckConstraint("kind in ('schema','mapping','rule')", name="ck_ontology_packages_kind"),
        CheckConstraint("stage in ('draft','review','staging','ga','deprecated')", name="ck_ontology_packages_stage"),
    )


class OntologyReleaseEventModel(Base):
    __tablename__ = "ontology_release_events"

    id = Column(String, primary_key=True)
    space_id = Column(String, ForeignKey("ontology_spaces.id"), nullable=False, index=True)
    package_id = Column(String, ForeignKey("ontology_packages.id"), nullable=True, index=True)

    kind = Column(String, nullable=False, index=True)
    version = Column(String, nullable=False)
    from_stage = Column(String, nullable=False)
    to_stage = Column(String, nullable=False)

    actor_user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    notes = Column(Text, nullable=True)
    warnings = Column(JSONB, nullable=False, default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OntologyApprovalModel(Base):
    __tablename__ = "ontology_approvals"

    id = Column(String, primary_key=True)
    space_id = Column(String, ForeignKey("ontology_spaces.id"), nullable=False, index=True)
    package_id = Column(String, ForeignKey("ontology_packages.id"), nullable=False, index=True)

    kind = Column(String, nullable=False, index=True)
    version = Column(String, nullable=False)
    requested_stage = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="pending", index=True)

    requester_user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    reviewer_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    request_note = Column(Text, nullable=True)
    review_note = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status in ('pending','approved','rejected')", name="ck_ontology_approvals_status"),
        CheckConstraint(
            "requested_stage in ('review','staging','ga','deprecated')",
            name="ck_ontology_approvals_requested_stage",
        ),
        Index(
            "uix_ontology_pending_approval_gate",
            "space_id",
            "kind",
            "version",
            "requested_stage",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )


class OntologyDecisionModel(Base):
    __tablename__ = "ontology_decisions"

    id = Column(String, primary_key=True)
    space_id = Column(String, ForeignKey("ontology_spaces.id"), nullable=False, index=True)
    rule_version = Column(String, nullable=False)
    risk_score = Column(Integer, nullable=False, default=0)
    risk_level = Column(String, nullable=False, default="low")

    hits = Column(JSONB, nullable=False, default=[])
    misses = Column(JSONB, nullable=False, default=[])
    graph_snapshot = Column(JSONB, nullable=False, default={})
    context = Column(JSONB, nullable=False, default={})

    created_by = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("risk_level in ('low','medium','high','critical')", name="ck_ontology_decisions_risk_level"),
    )


class OntologyExplanationModel(Base):
    __tablename__ = "ontology_explanations"

    decision_id = Column(String, ForeignKey("ontology_decisions.id", ondelete="CASCADE"), primary_key=True)
    why = Column(JSONB, nullable=False, default=[])
    why_not = Column(JSONB, nullable=False, default=[])
    evidence = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OntologyDataSourceModel(Base):
    __tablename__ = "ontology_data_sources"

    id = Column(String, primary_key=True)
    space_id = Column(String, ForeignKey("ontology_spaces.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False, index=True)
    protocol = Column(String, nullable=False, index=True)
    config = Column(JSONB, nullable=False, default={})
    secret_ref = Column(String, nullable=True)
    status = Column(String, nullable=False, default="draft", index=True)
    last_test_status = Column(String, nullable=True)
    last_test_message = Column(Text, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("space_id", "name", name="uix_ontology_data_source_space_name"),
        CheckConstraint("kind in ('database','api','protocol','file','stream')", name="ck_ontology_data_sources_kind"),
        CheckConstraint("status in ('draft','active','disabled')", name="ck_ontology_data_sources_status"),
    )


class OntologySecretModel(Base):
    __tablename__ = "ontology_secrets"

    id = Column(String, primary_key=True)
    space_id = Column(String, ForeignKey("ontology_spaces.id"), nullable=False, index=True)
    scope = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    encrypted_value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("space_id", "scope", "name", name="uix_ontology_secret_space_scope_name"),
    )
