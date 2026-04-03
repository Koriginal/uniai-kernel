from sqlalchemy import Column, String, DateTime, Text, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base
import uuid

class UserMemory(Base):
    """
    用户长期记忆模型
    
    存储从对话中提取的长期有效信息，如：
    - 用户偏好（编程语言、风格）
    - 基本信息（职业、背景）
    - 关键约束（格式要求、禁忌）
    - 历史事件（重要经历）
    
    配合向量索引实现语义检索。
    """
    __tablename__ = "user_memories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, index=True)
    
    content = Column(Text, nullable=False)  # 记忆内容："用户正在备考 CPA"
    category = Column(String, default="general")  # basic_info, preference, critical_constraint, work, history
    
    # 向量存储（PostgreSQL pgvector 扩展）
    # 注意：pgvector 的 vector 类型需要在迁移脚本中使用 text() 定义
    # embedding = Column(Vector(1536))  # 这里先不定义，在迁移脚本中用 SQL 添加
    
    # 记忆权重与溯源
    importance = Column(Integer, default=1)  # 1-5 权重，用于检索排序与淡忘逻辑
    source_session_id = Column(String, index=True, nullable=True) # 来源会话
    
    metadata_extra = Column(JSON, default={})  # 扩展字段：来源、置信度等
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<UserMemory(id={self.id}, user={self.user_id}, category={self.category})>"
