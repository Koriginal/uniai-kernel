from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from app.core.db import Base
import uuid


class AgentApplication(Base):
    """
    业务智能体应用。

    应用是业务场景入口，AgentProfile 是执行角色；这里负责把主控、
    工具、本体空间、runtime provider 和验收策略收拢到同一份配置。
    """
    __tablename__ = "agent_applications"

    id = Column(String, primary_key=True, default=lambda: f"app-{uuid.uuid4().hex[:8]}")
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    business_domain = Column(String, nullable=True)
    scenario_type = Column(String, nullable=False, default="custom")
    primary_agent_id = Column(String, ForeignKey("agent_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    runtime_provider_names = Column(JSON, default=[])
    tool_names = Column(JSON, default=[])
    ontology_space_id = Column(String, nullable=True, index=True)
    review_pack_id = Column(String, ForeignKey("review_packs.id", ondelete="SET NULL"), nullable=True, index=True)
    review_pack_version = Column(String, nullable=True)
    runtime_policy = Column(JSON, default={})
    acceptance_policy = Column(JSON, default={})
    status = Column(String, nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
