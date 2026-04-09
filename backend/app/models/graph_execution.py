from sqlalchemy import Column, String, DateTime, Float, JSON, Integer, func
from app.core.db import Base
import uuid

class GraphExecution(Base):
    """
    图节点执行遥测记录
    用于采集每个图节点的执行耗时、状态、Token 消耗等指标。
    """
    __tablename__ = "graph_executions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    session_id = Column(String, index=True, nullable=True) # 所属会话 ID
    request_id = Column(String, index=True, nullable=True) # 请求请求 ID
    
    node_name = Column(String, index=True, nullable=False) # 节点名称 (context, agent, tool_executor, etc.)
    agent_id = Column(String, index=True, nullable=True)   # 执行该节点时的 Agent ID
    
    status = Column(String, default="success")           # success, error, timeout
    duration_ms = Column(Float, default=0.0)             # 执行耗时 (毫秒)
    
    # 指标数据
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    tool_calls_count = Column(Integer, default=0)
    
    error_message = Column(String, nullable=True)         # 错误详情
    
    # 扩展元数据 (如节点输入/输出摘要、路由决策点等)
    metadata_extra = Column(JSON, default={})
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<GraphExecution(node={self.node_name}, status={self.status}, duration={self.duration_ms}ms)>"
