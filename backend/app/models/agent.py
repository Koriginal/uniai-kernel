from sqlalchemy import Column, String, Boolean, JSON, Text, ForeignKey, Integer
from sqlalchemy.orm import relationship
from app.core.db import Base
import uuid

class AgentProfile(Base):
    """
    智能体配置（Profile）
    
    核心实体，将模型、人设、工具集打包成一个可识别的 "Agent"。
    可以直接作为 OpenAI 协议中的 'model' 参数使用。
    """
    __tablename__ = "agent_profiles"
    
    # 外部暴露的唯一标识 (e.g., 'translator-gpt4', 'researcher-qwen')
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)  # 易读名称
    description = Column(Text, nullable=True)
    
    # 关联的模型配置（决定底层用哪个厂商/模型）
    model_config_id = Column(Integer, ForeignKey("provider_models.id", ondelete="SET NULL"), nullable=True)
    
    # 核心人设提示词 (System Prompt)
    system_prompt = Column(Text, nullable=True)
    
    # 授权使用的工具列表 (存储 PluginRegistry 中的工具名称，如 ["web_search", "memory_search"])
    # 如果为 None 或空列表，则不开启任何工具。如果包含 "*" 则开启全部（不推荐）。
    tools = Column(JSON, default=[])
    
    # [NEW] 角色定义：'orchestrator' (主控) 或 'expert' (专家)
    role = Column(String, default="expert", nullable=False)
    
    # [NEW] 专家接管的意图关键词列表
    routing_keywords = Column(JSON, default=[], nullable=False)
    
    # [NEW] 执行完毕后的控制权策略：'return' (归还) 或 'end' (结束)
    handoff_strategy = Column(String, default="return", nullable=False)
    
    # 私有性设置 (仍保留作为可见性控制，但不作为主控逻辑判断)
    is_public = Column(Boolean, default=False)
    
    is_active = Column(Boolean, default=True)
    
    # 关联
    model_config = relationship("ProviderModel")
    
    def __repr__(self):
        return f"<AgentProfile(id={self.id}, name={self.name}, user={self.user_id})>"
