"""add ontology governance constraints

Revision ID: c3f4a8b9d102
Revises: a4d8c7b1e902
Create Date: 2026-04-23 16:10:00

"""
from alembic import op
import sqlalchemy as sa


revision = "c3f4a8b9d102"
down_revision = "a4d8c7b1e902"
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint(
        "ck_ontology_packages_kind",
        "ontology_packages",
        "kind in ('schema','mapping','rule')",
    )
    op.create_check_constraint(
        "ck_ontology_packages_stage",
        "ontology_packages",
        "stage in ('draft','review','staging','ga','deprecated')",
    )
    op.create_check_constraint(
        "ck_ontology_approvals_status",
        "ontology_approvals",
        "status in ('pending','approved','rejected')",
    )
    op.create_check_constraint(
        "ck_ontology_approvals_requested_stage",
        "ontology_approvals",
        "requested_stage in ('review','staging','ga','deprecated')",
    )
    op.create_check_constraint(
        "ck_ontology_decisions_risk_level",
        "ontology_decisions",
        "risk_level in ('low','medium','high','critical')",
    )
    op.create_index(
        "uix_ontology_pending_approval_gate",
        "ontology_approvals",
        ["space_id", "kind", "version", "requested_stage"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade():
    op.drop_index("uix_ontology_pending_approval_gate", table_name="ontology_approvals")
    op.drop_constraint("ck_ontology_decisions_risk_level", "ontology_decisions", type_="check")
    op.drop_constraint("ck_ontology_approvals_requested_stage", "ontology_approvals", type_="check")
    op.drop_constraint("ck_ontology_approvals_status", "ontology_approvals", type_="check")
    op.drop_constraint("ck_ontology_packages_stage", "ontology_packages", type_="check")
    op.drop_constraint("ck_ontology_packages_kind", "ontology_packages", type_="check")
