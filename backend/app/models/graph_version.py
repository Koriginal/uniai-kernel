from sqlalchemy import Column, String, DateTime, JSON, Integer, func, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.core.db import Base

class GraphTopologyVersionModel(Base):
    """
    图拓扑版本快照模型
    支持多版本管理与手动/自动模式切换。
    实现“编排治理”的核心数据结构。
    """
    __tablename__ = "graph_topology_versions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(String, ForeignKey("graph_templates.id"), nullable=False)
    
    name = Column(String, nullable=True) # 版本简称或备注
    topology = Column(JSON, nullable=False) # 该版本的完整拓扑定义 (nodes + edges + layout)
    mode = Column(String, default="auto") # auto/manual
    
    version_code = Column(Integer, default=1) # 顺序版本号
    is_active = Column(Boolean, default=False) # 是否为当前生效版本
    
    user_id = Column(String, index=True, nullable=True) # 操作者
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系映射
    template = relationship("GraphTemplateModel", backref="versions")

    def __repr__(self):
        return f"<GraphTopologyVersion(id={self.id}, template={self.template_id}, mode={self.mode})>"
