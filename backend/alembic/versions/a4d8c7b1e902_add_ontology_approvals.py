"""add ontology approvals

Revision ID: a4d8c7b1e902
Revises: e1c3f9b6d2a1
Create Date: 2026-04-23 14:05:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'a4d8c7b1e902'
down_revision = 'e1c3f9b6d2a1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ontology_approvals',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('space_id', sa.String(), nullable=False),
        sa.Column('package_id', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('requested_stage', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('requester_user_id', sa.String(), nullable=False),
        sa.Column('reviewer_user_id', sa.String(), nullable=True),
        sa.Column('request_note', sa.Text(), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['space_id'], ['ontology_spaces.id']),
        sa.ForeignKeyConstraint(['package_id'], ['ontology_packages.id']),
        sa.ForeignKeyConstraint(['requester_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['reviewer_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ontology_approvals_space_id'), 'ontology_approvals', ['space_id'], unique=False)
    op.create_index(op.f('ix_ontology_approvals_package_id'), 'ontology_approvals', ['package_id'], unique=False)
    op.create_index(op.f('ix_ontology_approvals_kind'), 'ontology_approvals', ['kind'], unique=False)
    op.create_index(op.f('ix_ontology_approvals_requested_stage'), 'ontology_approvals', ['requested_stage'], unique=False)
    op.create_index(op.f('ix_ontology_approvals_status'), 'ontology_approvals', ['status'], unique=False)
    op.create_index(op.f('ix_ontology_approvals_requester_user_id'), 'ontology_approvals', ['requester_user_id'], unique=False)
    op.create_index(op.f('ix_ontology_approvals_reviewer_user_id'), 'ontology_approvals', ['reviewer_user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_ontology_approvals_reviewer_user_id'), table_name='ontology_approvals')
    op.drop_index(op.f('ix_ontology_approvals_requester_user_id'), table_name='ontology_approvals')
    op.drop_index(op.f('ix_ontology_approvals_status'), table_name='ontology_approvals')
    op.drop_index(op.f('ix_ontology_approvals_requested_stage'), table_name='ontology_approvals')
    op.drop_index(op.f('ix_ontology_approvals_kind'), table_name='ontology_approvals')
    op.drop_index(op.f('ix_ontology_approvals_package_id'), table_name='ontology_approvals')
    op.drop_index(op.f('ix_ontology_approvals_space_id'), table_name='ontology_approvals')
    op.drop_table('ontology_approvals')
