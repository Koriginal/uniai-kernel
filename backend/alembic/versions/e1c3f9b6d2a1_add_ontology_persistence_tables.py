"""add ontology persistence tables

Revision ID: e1c3f9b6d2a1
Revises: ab7102e662ea
Create Date: 2026-04-23 12:30:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'e1c3f9b6d2a1'
down_revision = 'ab7102e662ea'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ontology_spaces',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner_user_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_user_id', 'code', name='uix_ontology_space_owner_code'),
    )
    op.create_index(op.f('ix_ontology_spaces_owner_user_id'), 'ontology_spaces', ['owner_user_id'], unique=False)

    op.create_table(
        'ontology_packages',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('space_id', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('stage', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['space_id'], ['ontology_spaces.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('space_id', 'kind', 'version', name='uix_ontology_pkg_space_kind_version'),
    )
    op.create_index(op.f('ix_ontology_packages_space_id'), 'ontology_packages', ['space_id'], unique=False)
    op.create_index(op.f('ix_ontology_packages_kind'), 'ontology_packages', ['kind'], unique=False)
    op.create_index(op.f('ix_ontology_packages_stage'), 'ontology_packages', ['stage'], unique=False)
    op.create_index(op.f('ix_ontology_packages_is_active'), 'ontology_packages', ['is_active'], unique=False)
    op.create_index('ix_ontology_pkg_space_kind_stage', 'ontology_packages', ['space_id', 'kind', 'stage'], unique=False)
    op.create_index(
        'uix_ontology_pkg_single_active',
        'ontology_packages',
        ['space_id', 'kind'],
        unique=True,
        postgresql_where=sa.text('is_active = true'),
    )

    op.create_table(
        'ontology_release_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('space_id', sa.String(), nullable=False),
        sa.Column('package_id', sa.String(), nullable=True),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('from_stage', sa.String(), nullable=False),
        sa.Column('to_stage', sa.String(), nullable=False),
        sa.Column('actor_user_id', sa.String(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['package_id'], ['ontology_packages.id']),
        sa.ForeignKeyConstraint(['space_id'], ['ontology_spaces.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ontology_release_events_space_id'), 'ontology_release_events', ['space_id'], unique=False)
    op.create_index(op.f('ix_ontology_release_events_package_id'), 'ontology_release_events', ['package_id'], unique=False)
    op.create_index(op.f('ix_ontology_release_events_kind'), 'ontology_release_events', ['kind'], unique=False)
    op.create_index(op.f('ix_ontology_release_events_actor_user_id'), 'ontology_release_events', ['actor_user_id'], unique=False)

    op.create_table(
        'ontology_decisions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('space_id', sa.String(), nullable=False),
        sa.Column('rule_version', sa.String(), nullable=False),
        sa.Column('risk_score', sa.Integer(), nullable=False),
        sa.Column('risk_level', sa.String(), nullable=False),
        sa.Column('hits', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('misses', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('graph_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['space_id'], ['ontology_spaces.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ontology_decisions_space_id'), 'ontology_decisions', ['space_id'], unique=False)
    op.create_index(op.f('ix_ontology_decisions_created_by'), 'ontology_decisions', ['created_by'], unique=False)

    op.create_table(
        'ontology_explanations',
        sa.Column('decision_id', sa.String(), nullable=False),
        sa.Column('why', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('why_not', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['decision_id'], ['ontology_decisions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('decision_id'),
    )


def downgrade():
    op.drop_table('ontology_explanations')

    op.drop_index(op.f('ix_ontology_decisions_created_by'), table_name='ontology_decisions')
    op.drop_index(op.f('ix_ontology_decisions_space_id'), table_name='ontology_decisions')
    op.drop_table('ontology_decisions')

    op.drop_index(op.f('ix_ontology_release_events_actor_user_id'), table_name='ontology_release_events')
    op.drop_index(op.f('ix_ontology_release_events_kind'), table_name='ontology_release_events')
    op.drop_index(op.f('ix_ontology_release_events_package_id'), table_name='ontology_release_events')
    op.drop_index(op.f('ix_ontology_release_events_space_id'), table_name='ontology_release_events')
    op.drop_table('ontology_release_events')

    op.drop_index('ix_ontology_pkg_space_kind_stage', table_name='ontology_packages')
    op.drop_index('uix_ontology_pkg_single_active', table_name='ontology_packages')
    op.drop_index(op.f('ix_ontology_packages_is_active'), table_name='ontology_packages')
    op.drop_index(op.f('ix_ontology_packages_stage'), table_name='ontology_packages')
    op.drop_index(op.f('ix_ontology_packages_kind'), table_name='ontology_packages')
    op.drop_index(op.f('ix_ontology_packages_space_id'), table_name='ontology_packages')
    op.drop_table('ontology_packages')

    op.drop_index(op.f('ix_ontology_spaces_owner_user_id'), table_name='ontology_spaces')
    op.drop_table('ontology_spaces')
