"""add_user_memory_and_session_context

Revision ID: ded05a092a6f
Revises: ba918c030aa0
Create Date: 2026-01-15 14:26:54.306948

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ded05a092a6f'
down_revision = 'ba918c030aa0'
branch_labels = None
depends_on = None


def upgrade():
    # 1. 启用 pgvector 扩展
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    
    # 2. 创建 user_memories 表
    op.create_table(
        'user_memories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('category', sa.String(), server_default='general'),
        sa.Column('metadata_extra', postgresql.JSON(astext_type=sa.Text()), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()'))
    )
    
    # 添加向量列（使用 pgvector 的 vector 类型）
    op.execute('ALTER TABLE user_memories ADD COLUMN embedding vector(1536)')
    
    # 创建索引
    op.create_index('ix_user_memories_user_id', 'user_memories', ['user_id'])
    op.execute('CREATE INDEX ON user_memories USING hnsw (embedding vector_cosine_ops)')
    
    # 3. 扩展 chat_sessions 表
    op.add_column('chat_sessions', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('chat_sessions', sa.Column('compression_count', sa.Integer(), server_default='0'))


def downgrade():
    # 回滚操作
    op.drop_column('chat_sessions', 'compression_count')
    op.drop_column('chat_sessions', 'summary')
    
    op.drop_index('ix_user_memories_user_id', table_name='user_memories')
    op.execute('DROP INDEX IF EXISTS user_memories_embedding_idx')
    op.drop_table('user_memories')
    
    op.execute('DROP EXTENSION IF EXISTS vector')
