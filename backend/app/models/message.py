from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey
from sqlalchemy.sql import func
from app.core.db import Base
import uuid

class ChatMessage(Base):
    """
    聊天消息模型
    
    存储用户和 AI 的对话历史，支持：
    - 会话关联
    - Token 计数
    - 时间戳
    """
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    role = Column(String, nullable=False)  # "user" | "assistant" | "system"
    content = Column(Text, nullable=False)
    
    user_id = Column(String, nullable=True, index=True)  # 用于跨会话检索
    agent_id = Column(String, nullable=True, index=True)  # 此消息对应的 Agent ID
    
    token_count = Column(Integer, default=0)  # Token 消耗
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<ChatMessage(id={self.id}, role={self.role}, session={self.session_id})>"
