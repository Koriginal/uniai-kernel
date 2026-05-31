import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.core.db import Base


class ToolArtifact(Base):
    """
    工具执行产物。

    tool_runtime_events 只保存短摘要和索引字段，完整结果放在这里，避免长 JSON、
    搜索结果或文件片段直接进入消息上下文。
    """
    __tablename__ = "tool_artifacts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String, ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(String, nullable=True, index=True)
    agent_id = Column(String, nullable=True, index=True)
    request_id = Column(String, nullable=True, index=True)
    tool_call_id = Column(String, nullable=True, index=True)
    tool_name = Column(String, nullable=False, index=True)
    content_type = Column(String, nullable=False, default="application/json")
    preview = Column(Text, nullable=True)
    content = Column(JSON, nullable=True)
    artifact_metadata = Column(JSON, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def __repr__(self):
        return f"<ToolArtifact(id={self.id}, tool={self.tool_name}, session={self.session_id})>"
