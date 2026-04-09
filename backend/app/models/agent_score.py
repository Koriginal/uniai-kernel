from sqlalchemy import Column, String, DateTime, Float, JSON, Integer, func, ForeignKey
from app.core.db import Base
import uuid

class AgentScoreHistory(Base):
    """
    Agent 能力评分历史
    记录各 Agent 的成功率、响应耗时、质量分以及擅长领域。
    """
    __tablename__ = "agent_score_history"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, index=True, nullable=False) # 对应 AgentProfile.id
    
    total_calls = Column(Integer, default=0)
    success_rate = Column(Float, default=0.0)
    avg_duration_ms = Column(Float, default=0.0)
    avg_quality_score = Column(Float, default=0.0) # 用户反馈或 LLM 评估分 (0-1)
    
    specialties = Column(JSON, default=[]) # 擅长领域标签 ["coding", "logic", ...]
    
    computed_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AgentScoreHistory(agent={self.agent_id}, score={self.avg_quality_score})>"
