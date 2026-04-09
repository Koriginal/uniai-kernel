"""
图拓扑与调试 API

提供前端可视化所需的图结构数据。
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, update, desc

from app.agents.graph_builder import get_graph_mermaid
from app.agents.health_monitor import health_monitor
from app.core.db import SessionLocal, get_db
from app.models.graph_version import GraphTopologyVersionModel
from app.schemas.graph import GraphTopologyVersion, GraphTopologyVersionCreate, GraphTopologyVersionList
from app.agents.graph_registry import graph_registry

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/topology")
async def get_graph_topology():
    """
    返回当前对话图的 Mermaid 表示。

    前端可直接将此字符串渲染为可视化流程图。
    """
    mermaid = await get_graph_mermaid()
    return {
        "mermaid": mermaid,
        "nodes": ["context", "agent", "tool_executor", "handoff", "synthesize"],
        "description": "UniAI LangGraph 对话状态图"
    }


@router.get("/nodes")
async def get_graph_nodes():
    """
    返回图中所有节点的描述信息，用于前端展示节点说明。
    """
    return {
        "nodes": [
            {
                "id": "context",
                "label": "上下文构建",
                "description": "加载会话记忆、历史消息，注入 System Prompt，创建助手消息气泡",
                "icon": "📥",
                "color": "#52c41a"
            },
            {
                "id": "agent",
                "label": "LLM 推理",
                "description": "调用大语言模型进行思考，产出文本回复或工具调用指令",
                "icon": "🤖",
                "color": "#1890ff"
            },
            {
                "id": "tool_executor",
                "label": "工具执行",
                "description": "并行执行模型请求的工具（搜索、Canvas、自定义工具等）",
                "icon": "🔧",
                "color": "#fa8c16"
            },
            {
                "id": "handoff",
                "label": "专家路由",
                "description": "将任务移交给指定领域专家，切换活跃智能体身份",
                "icon": "🤝",
                "color": "#722ed1"
            },
            {
                "id": "synthesize",
                "label": "汇总归还",
                "description": "专家完成后关闭协作区块，将控制权归还给主控智能体",
                "icon": "📝",
                "color": "#eb2f96"
            }
        ]
    }


@router.get("/metrics")
async def get_graph_metrics(window: int = 60):
    """
    返回最近 N 分钟的图执行指标。
    """
    async with SessionLocal() as db:
        stats = await health_monitor.get_node_stats(db, window)
        return stats


@router.get("/versions", response_model=GraphTopologyVersionList)
async def list_graph_versions(
    template_id: str = "standard",
    db: Session = Depends(get_db)
):
    """
    列出指定模板的所有拓扑历史版本。
    """
    stmt = select(GraphTopologyVersionModel).where(
        GraphTopologyVersionModel.template_id == template_id
    ).order_by(desc(GraphTopologyVersionModel.created_at))
    
    result = await db.execute(stmt)
    versions = result.scalars().all()
    
    active_version = next((v for v in versions if v.is_active), None)
    
    return {
        "versions": versions,
        "active_version_id": active_version.id if active_version else None
    }


@router.post("/versions", response_model=GraphTopologyVersion)
async def save_graph_version(
    version_in: GraphTopologyVersionCreate,
    template_id: str = "standard",
    db: Session = Depends(get_db)
):
    """
    保存当前拓扑为一个新版本快照。
    """
    # 1. 获取当前最大版本号
    stmt = select(GraphTopologyVersionModel).where(
        GraphTopologyVersionModel.template_id == template_id
    ).order_by(desc(GraphTopologyVersionModel.version_code))
    
    last_ver_res = await db.execute(stmt)
    last_ver = last_ver_res.scalars().first()
    new_code = (last_ver.version_code + 1) if last_ver else 1

    # 2. 如果新版本设为 active，需要取消之前的所有 active
    if version_in.is_active:
        await db.execute(
            update(GraphTopologyVersionModel)
            .where(GraphTopologyVersionModel.template_id == template_id)
            .values(is_active=False)
        )

    # 3. 创建新纪录
    new_version = GraphTopologyVersionModel(
        template_id=template_id,
        name=version_in.name or f"Version {new_code}",
        topology=version_in.topology,
        mode=version_in.mode,
        version_code=new_code,
        is_active=version_in.is_active
    )
    
    db.add(new_version)
    await db.commit()
    await db.refresh(new_version)
    
    # 刷新注册中心缓存
    if version_in.is_active:
        graph_registry.invalidate_cache(template_id)
        
    return new_version


@router.post("/versions/{version_id}/active")
async def activate_graph_version(
    version_id: int,
    template_id: str = "standard",
    db: Session = Depends(get_db)
):
    """
    将指定的历史版本设为当前活跃版本。
    """
    # 1. 验证版本是否存在且匹配模板
    stmt = select(GraphTopologyVersionModel).where(
        and_(
            GraphTopologyVersionModel.id == version_id,
            GraphTopologyVersionModel.template_id == template_id
        )
    )
    res = await db.execute(stmt)
    version = res.scalar_one_or_none()
    
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    # 2. 批量重置并激活目标
    await db.execute(
        update(GraphTopologyVersionModel)
        .where(GraphTopologyVersionModel.template_id == template_id)
        .values(is_active=False)
    )
    
    version.is_active = True
    await db.commit()
    
    # 刷新注册中心缓存
    graph_registry.invalidate_cache(template_id)
    
    return {"status": "success", "active_version_id": version.id, "mode": version.mode}
