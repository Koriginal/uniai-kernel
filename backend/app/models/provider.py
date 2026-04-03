from sqlalchemy import Column, Integer, String, Boolean, JSON, Text, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.orm import relationship
from app.core.db import Base
from datetime import datetime, timezone

class ProviderTemplate(Base):
    """
    系统级供应商模板
    管理员预设的供应商配置模板，用户可基于此创建自己的配置。
    """
    __tablename__ = "provider_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    provider_type = Column(String, nullable=False)  # openai, anthropic, gemini...
    
    api_base = Column(String, nullable=True)
    is_free = Column(Boolean, default=False)
    requires_api_key = Column(Boolean, default=True)
    config_schema = Column(JSON, default={})
    supported_models = Column(JSON, default=[])  # 预置模型列表（含上下文长度）
    description = Column(Text, nullable=True)
    logo_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<ProviderTemplate(name={self.name}, type={self.provider_type})>"


class UserProvider(Base):
    """
    用户级供应商配置
    每个用户可以配置自己的 API Key、自定义 API Base 等参数。
    """
    __tablename__ = "user_providers"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    template_id = Column(Integer, ForeignKey("provider_templates.id"), nullable=True)  # 可为空（完全自定义）
    
    # 用户自定义信息
    display_name = Column(String, nullable=True)  # 用户起的名字
    custom_api_base = Column(String, nullable=True)  # 覆写模板默认的 API Base
    api_key_encrypted = Column(Text, nullable=True)
    custom_config = Column(JSON, default={})
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    template = relationship("ProviderTemplate")
    models = relationship("ProviderModel", back_populates="provider", cascade="all, delete-orphan")

    @property
    def effective_api_base(self):
        """优先取用户自定义，否则取模板默认"""
        return self.custom_api_base or (self.template.api_base if self.template else None)

    @property
    def effective_name(self):
        return self.display_name or (self.template.name if self.template else f"Provider-{self.id}")

    def __repr__(self):
        return f"<UserProvider(user_id={self.user_id}, name={self.effective_name})>"


class ProviderModel(Base):
    """
    供应商下的模型配置
    每个供应商可以挂载多个模型，支持独立配置上下文长度、能力类型等。
    """
    __tablename__ = "provider_models"
    
    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("user_providers.id", ondelete="CASCADE"), nullable=False)
    
    model_name = Column(String, nullable=False)  # e.g. "gpt-4-turbo"
    model_type = Column(String, default="llm")  # llm, embedding, tts, stt, vision
    context_length = Column(Integer, default=4096)
    max_output_tokens = Column(Integer, nullable=True)
    is_default = Column(Boolean, default=False)
    
    provider = relationship("UserProvider", back_populates="models")
    
    __table_args__ = (
        UniqueConstraint('provider_id', 'model_name', name='uix_provider_model'),
    )
    
    def __repr__(self):
        return f"<ProviderModel(name={self.model_name}, type={self.model_type}, ctx={self.context_length})>"


class UserModelConfig(Base):
    """用户默认模型配置（各类任务的默认模型）"""
    __tablename__ = "user_model_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    model_type = Column(String, nullable=False)
    default_model_name = Column(String, nullable=False)
    provider_id = Column(Integer, ForeignKey("user_providers.id"), nullable=False)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'model_type', name='uix_user_model_type'),
    )
    
    provider = relationship("UserProvider")

