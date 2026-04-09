from sqlalchemy import Column, String, DateTime, JSON, Integer, func, Boolean
from app.core.db import Base

class GraphTemplateModel(Base):
    """
    图拓扑模板模型
    支持用户自定义图结构 (Nodes + Edges)。
    """
    __tablename__ = "graph_templates"
    
    id = Column(String, primary_key=True) # 模板唯一标识 (如 'standard', 'rag-flow')
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    
    user_id = Column(String, index=True, nullable=True) # 所有者 (None 表示系统内置)
    
    topology = Column(JSON, nullable=False) # 完整的图拓扑定义
    # Schema 示例:
    # {
    #   "nodes": [{"id": "n1", "type": "agent", "config": {...}}],
    #   "edges": [{"source": "n1", "target": "n2"}],
    #   "entry_point": "n1"
    # }
    
    is_system = Column(Boolean, default=False) # 是否系统内置
    is_active = Column(Boolean, default=True)
    
    version = Column(Integer, default=1)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<GraphTemplate(id={self.id}, name={self.name})>"
