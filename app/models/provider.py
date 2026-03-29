from sqlalchemy import Column, Integer, String, Boolean, JSON, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.db import Base

class ProviderTemplate(Base):
    """
    系统级供应商模板
    
    管理员预设的供应商配置模板，用户可基于此创建自己的配置。
    """
    __tablename__ = "provider_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)  # e.g., "OpenAI", "DeepSeek"
    provider_type = Column(String, nullable=False)  # openai, azure, anthropic...
    
    # 默认配置
    api_base = Column(String, nullable=True)
    is_free = Column(Boolean, default=False)  # 是否免费
    requires_api_key = Column(Boolean, default=True)  # 是否需要用户提供 API Key
    
    # 配置结构（JSON Schema）
    config_schema = Column(JSON, default={})  # {"api_key": {"required": true}, ...}
    
    # 支持的模型列表
    supported_models = Column(JSON, default=[])  # ["gpt-4", "gpt-3.5-turbo"]
    
    # 描述信息
    description = Column(Text, nullable=True)
    logo_url = Column(String, nullable=True)
    
    is_active = Column(Boolean, default=True)
    
    def __repr__(self):
        return f"<ProviderTemplate(name={self.name}, type={self.provider_type})>"


class UserProvider(Base):
    """
    用户级供应商配置
    
    每个用户可以配置自己的 API Key 和自定义参数。
    """
    __tablename__ = "user_providers"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)  # 用户/租户 ID
    template_id = Column(Integer, ForeignKey("provider_templates.id"), nullable=False)
    
    # 用户自己的加密 API Key
    api_key_encrypted = Column(Text, nullable=True)
    
    # 用户自定义配置（覆盖模板默认值）
    custom_config = Column(JSON, default={})
    
    is_active = Column(Boolean, default=True)
    
    # 关联
    template = relationship("ProviderTemplate")
    
    def __repr__(self):
        return f"<UserProvider(user_id={self.user_id}, template_id={self.template_id})>"


class UserModelConfig(Base):
    """
    用户默认模型配置
    
    用户为不同类型任务设置的默认模型。
    """
    __tablename__ = "user_model_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    
    # 模型类型：llm, embedding, tts, stt
    model_type = Column(String, nullable=False)
    
    # 默认模型名称
    default_model_name = Column(String, nullable=False)
    
    # 关联的用户供应商
    provider_id = Column(Integer, ForeignKey("user_providers.id"), nullable=False)
    
    # 唯一约束：每个用户每种类型只能有一个默认模型
    __table_args__ = (
        UniqueConstraint('user_id', 'model_type', name='uix_user_model_type'),
    )
    
    provider = relationship("UserProvider")
    
    def __repr__(self):
        return f"<UserModelConfig(user={self.user_id}, type={self.model_type}, model={self.default_model_name})>"
