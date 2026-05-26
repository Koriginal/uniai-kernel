"""add chat message runtime events

Revision ID: f4a9c8d2b671
Revises: e7b4c2d9a113
Create Date: 2026-05-06 15:10:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f4a9c8d2b671"
down_revision = "e7b4c2d9a113"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def upgrade():
    if not _column_exists("chat_messages", "runtime_events"):
        op.add_column(
            "chat_messages",
            sa.Column(
                "runtime_events",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )


def downgrade():
    if _column_exists("chat_messages", "runtime_events"):
        op.drop_column("chat_messages", "runtime_events")
