import logging
from typing import Dict, Any, Optional, List
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver

from app.core.graph_state import AgentGraphState
from app.agents.pg_checkpointer import create_pg_checkpointer
from app.models.graph_template import GraphTemplateModel
from app.models.graph_version import GraphTopologyVersionModel
from app.core.db import SessionLocal
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)

class GraphRegistry:
    """
    图模板注册中心
    负责动态解析拓扑定义并生成可执行的 LangGraph 实例。
    实现“编排自进化”的核心基础设施。
    """
    
    def __init__(self):
        self._compiled_cache: Dict[str, Any] = {}

    async def get_compiled_graph(self, template_id: str = "standard"):
        """
        获取编译后的图实例（带缓存）。
        当 template_id="standard" 时，目前的逻辑仍指向写死的 graph_builder。
        """
        if template_id in self._compiled_cache:
            return self._compiled_cache[template_id]
            
        # 1. 尝试从数据库加载自定义配置（版本优先）
        async with SessionLocal() as db:
            # 优先查找该模板下的活跃版本
            version_stmt = select(GraphTopologyVersionModel).where(
                and_(
                    GraphTopologyVersionModel.template_id == template_id,
                    GraphTopologyVersionModel.is_active == True
                )
            )
            version_res = await db.execute(version_stmt)
            active_version = version_res.scalar_one_or_none()
            
            if active_version:
                logger.info(f"[GraphRegistry] Compiling from ACTIVE VERSION for template: {template_id} (Mode: {active_version.mode})")
                graph = await self._compile_from_topology(active_version.topology)
                self._compiled_cache[template_id] = graph
                return graph

            # 如果没有活跃版本，退而求其次查找基础模板定义
            stmt = select(GraphTemplateModel).where(GraphTemplateModel.id == template_id)
            result = await db.execute(stmt)
            template = result.scalar_one_or_none()
            
        if template:
            # 2. 动态编译基础模板
            logger.info(f"[GraphRegistry] Compiling from BASE TEMPLATE: {template_id}")
            graph = await self._compile_from_topology(template.topology)
            self._compiled_cache[template_id] = graph
            return graph
            
        # 3. 如果没找到，返回默认图 (这里也可以整合 graph_builder 逻辑)
        from app.agents.graph_builder import build_conversation_graph
        return await build_conversation_graph()

    async def initialize_system_templates(self):
        """
        初始化系统内置模板到数据库。
        """
        from langgraph.graph import END
        standard_topology = {
            "nodes": [
                {"id": "context", "type": "context"},
                {"id": "agent", "type": "agent"},
                {"id": "tool_executor", "type": "tool_executor"},
                {"id": "handoff", "type": "handoff"},
                {"id": "synthesize", "type": "synthesize"}
            ],
            "edges": [
                {"source": "context", "target": "agent"},
                {"source": "synthesize", "target": "agent"}
            ],
            "conditional_edges": [
                {
                    "source": "agent",
                    "type": "adaptive_router",
                    "mapping": {
                        "handoff": "handoff",
                        "tool_executor": "tool_executor",
                        "synthesize": "synthesize",
                        "__end__": "__end__"
                    }
                },
                {
                    "source": "tool_executor",
                    "type": "fixed",
                    "target": "agent"
                },
                {
                    "source": "handoff",
                    "type": "fixed",
                    "target": "agent"
                }
            ],
            "entry_point": "context"
        }
        
        async with SessionLocal() as db:
            try:
                # 强制刷新/同步标准模板
                stmt = select(GraphTemplateModel).where(GraphTemplateModel.id == "standard")
                res = await db.execute(stmt)
                existing = res.scalar_one_or_none()
                
                if not existing:
                    logger.info("[GraphRegistry] Initializing 'standard' graph template...")
                    standard = GraphTemplateModel(
                        id="standard",
                        name="Standard Swarm Flow",
                        description="默认的专家协作与自愈流程",
                        topology=standard_topology,
                        is_system=True
                    )
                    db.add(standard)
                else:
                    logger.info("[GraphRegistry] Refreshing 'standard' graph template definition...")
                    existing.topology = standard_topology
                    existing.name = "Standard Swarm Flow"
                
                await db.commit()
                # 刷新缓存
                self.invalidate_cache("standard")
            except Exception as e:
                logger.error(f"[GraphRegistry] Failed to sync system templates: {e}")
                await db.rollback()
            finally:
                await db.close()

    async def _compile_from_topology(self, topology: Dict[str, Any]):
        """
        从拓扑 JSON 定义编译图。
        核心逻辑：映射节点 ID 到实际函数，构建边。
        """
        workflow = StateGraph(AgentGraphState)
        
        # 节点注册逻辑需映射 type 到实际函数 (此处简化演示，未来可扩展节点插件)
        from app.agents.graph_builder import wrap_telemetry
        from app.agents.nodes import (
            context_node, agent_node, tool_executor_node, handoff_node, synthesize_node
        )
        
        node_factory = {
            "context": context_node,
            "agent": agent_node,
            "tool_executor": tool_executor_node,
            "handoff": handoff_node,
            "synthesize": synthesize_node
        }
        
        # 解析 nodes
        for node_def in topology.get("nodes", []):
            nid = node_def["id"]
            ntype = node_def["type"]
            func = node_factory.get(ntype)
            if func:
                workflow.add_node(nid, wrap_telemetry(func, nid))
        
        # 解析 edges (固定边)
        for edge_def in topology.get("edges", []):
            workflow.add_edge(edge_def["source"], edge_def["target"])

        # 解析 conditional_edges (条件边)
        from app.agents.graph_builder import adaptive_route, route_after_tools, route_after_handoff
        from langgraph.graph import END

        for ce_def in topology.get("conditional_edges", []):
            source = ce_def["source"]
            ctype = ce_def["type"]
            
            if ctype == "adaptive_router":
                mapping = ce_def.get("mapping", {})
                # 转换 __end__ 字符串为 END 常量
                real_mapping = {k: (END if v == "__end__" else v) for k, v in mapping.items()}
                workflow.add_conditional_edges(source, adaptive_route, real_mapping)
            
            elif ctype == "fixed":
                # 处理像 tool_executor -> agent 这种虽然固定但通常用条件边包装的
                target = ce_def["target"]
                if source == "tool_executor":
                    workflow.add_conditional_edges(source, route_after_tools, {target: target})
                elif source == "handoff":
                    workflow.add_conditional_edges(source, route_after_handoff, {target: target})
                else:
                    # 默认情况支持简单映射
                    workflow.add_conditional_edges(source, lambda x: target, {target: target})
            
        workflow.set_entry_point(topology.get("entry_point", "context"))
        
        # 持久化支持
        checkpointer = await create_pg_checkpointer()
        return workflow.compile(checkpointer=checkpointer)

    def invalidate_cache(self, template_id: str):
        if template_id in self._compiled_cache:
            del self._compiled_cache[template_id]

# 全局单例
graph_registry = GraphRegistry()
