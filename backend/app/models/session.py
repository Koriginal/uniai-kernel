from sqlalchemy import Column, String, DateTime, Text, JSON, Integer
from sqlalchemy.sql import func
from app.core.db import Base
import uuid

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    # 使用 UUID 字符串作为主键，直接对应 Agent 的 thread_id
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    title = Column(String, nullable=True, default="New Chat")
    opening_remarks = Column(Text, nullable=True) # 开场白 / System Prompt
    
    user_id = Column(String, nullable=True) # 预留用户ID
    active_agent_id = Column(String, nullable=True) # 当前活跃的智能体 ID (Swarm 令牌)
    
    # 上下文管理字段
    summary = Column(Text, nullable=True)  # 会话滚动摘要
    compression_count = Column(Integer, default=0)  # 压缩次数
    
    extra_metadata = Column(JSON, default={}) # 扩展字段
    
    # 状态机扩展字段
    status = Column(String, default="active") # active, paused, interrupted, completed
    thread_state = Column(JSON, default={}) # 存储执行上下文、Checkpoints 等快照信息
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
