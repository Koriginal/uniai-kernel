"""add org tenancy foundation

Revision ID: d8f1c4e2ab77
Revises: c3f4a8b9d102
Create Date: 2026-04-23 18:05:00

"""
from alembic import op
import sqlalchemy as sa


revision = "d8f1c4e2ab77"
down_revision = "c3f4a8b9d102"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_organizations_code"), "organizations", ["code"], unique=True)
    op.create_index(op.f("ix_organizations_owner_user_id"), "organizations", ["owner_user_id"], unique=False)

    op.create_table(
        "user_organization_memberships",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="member"),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "user_id", name="uix_org_user_membership"),
    )
    op.create_index(op.f("ix_user_organization_memberships_org_id"), "user_organization_memberships", ["org_id"], unique=False)
    op.create_index(op.f("ix_user_organization_memberships_user_id"), "user_organization_memberships", ["user_id"], unique=False)

    op.add_column("ontology_spaces", sa.Column("org_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_ontology_spaces_org_id_organizations",
        "ontology_spaces",
        "organizations",
        ["org_id"],
        ["id"],
    )
    op.create_index(op.f("ix_ontology_spaces_org_id"), "ontology_spaces", ["org_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_ontology_spaces_org_id"), table_name="ontology_spaces")
    op.drop_constraint("fk_ontology_spaces_org_id_organizations", "ontology_spaces", type_="foreignkey")
    op.drop_column("ontology_spaces", "org_id")

    op.drop_index(op.f("ix_user_organization_memberships_user_id"), table_name="user_organization_memberships")
    op.drop_index(op.f("ix_user_organization_memberships_org_id"), table_name="user_organization_memberships")
    op.drop_table("user_organization_memberships")

    op.drop_index(op.f("ix_organizations_owner_user_id"), table_name="organizations")
    op.drop_index(op.f("ix_organizations_code"), table_name="organizations")
    op.drop_table("organizations")
