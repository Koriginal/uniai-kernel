from sqlalchemy import Column, String, JSON, DateTime, Float, ForeignKey
from sqlalchemy.sql import func
from app.core.db import Base
import uuid

class ActionLog(Base):
    """
    行动执行审计日志 (Action Execution Audit Log)
    提供生产级的全链路追踪与可观测性能力。
    """
    __tablename__ = "action_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # 上下文关联
    session_id = Column(String, index=True, nullable=True)
    user_id = Column(String, index=True)
    agent_id = Column(String, index=True, nullable=True) # 哪个智能体调用的
    
    # 行动详情
    action_name = Column(String, index=True)
    input_params = Column(JSON)
    output_result = Column(String) # 存储结果摘要或全文
    
    # 性能与状态
    status = Column(String) # success, failed
    duration_ms = Column(Float)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
