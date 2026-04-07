from sqlalchemy import Column, String, JSON, DateTime, Boolean, func
from app.core.db import Base
import uuid

class DynamicTool(Base):
    """
    动态注册的工具 (API / MCP / CLI)
    """
    __tablename__ = "dynamic_tools"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    name = Column(String, unique=True, index=True, nullable=False)
    label = Column(String)
    description = Column(String)
    category = Column(String, default="custom")
    
    # 类型: api, mcp, cli
    tool_type = Column(String, nullable=False)
    
    # 配置信息 (如 API URL, MCP Coammand, CLI Script 等)
    config = Column(JSON, default={})
    
    # OpenAI 格式的参数 Schema
    parameters_schema = Column(JSON, default={"type": "object", "properties": {}})
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
