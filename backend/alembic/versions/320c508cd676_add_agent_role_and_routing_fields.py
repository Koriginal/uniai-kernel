"""add_agent_role_and_routing_fields

Revision ID: 320c508cd676
Revises: c0e38764a330
Create Date: 2026-04-09 13:22:24.500211

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '320c508cd676'
down_revision = 'c0e38764a330'
branch_labels = None
depends_on = None


def upgrade():
    # 按照先后顺序：先允许 NULL 添加列，然后填充数据，最后设为 NOT NULL
    op.add_column('agent_profiles', sa.Column('role', sa.String(), nullable=True))
    op.add_column('agent_profiles', sa.Column('routing_keywords', sa.JSON(), nullable=True))
    op.add_column('agent_profiles', sa.Column('handoff_strategy', sa.String(), nullable=True))
    
    # [关键] 根据 current 项目逻辑填充旧数据：如果 is_public 为 True 则可能是主控（暂时这么假设以平滑过渡）
    # 但根据用户要求，现在起所有专家默认为 'expert'，'UniAI 总控助手' 需要手动设为 'orchestrator'
    # 填充默认值
    op.execute("UPDATE agent_profiles SET role = 'expert'")
    op.execute("UPDATE agent_profiles SET routing_keywords = '[]'")
    op.execute("UPDATE agent_profiles SET handoff_strategy = 'return'")
    
    # 设为 NOT NULL
    op.alter_column('agent_profiles', 'role', nullable=False)
    op.alter_column('agent_profiles', 'routing_keywords', nullable=False)
    op.alter_column('agent_profiles', 'handoff_strategy', nullable=False)


def downgrade():
    op.drop_column('agent_profiles', 'handoff_strategy')
    op.drop_column('agent_profiles', 'routing_keywords')
    op.drop_column('agent_profiles', 'role')
