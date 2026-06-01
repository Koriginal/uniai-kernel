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
from app.agents.task_runtime import get_runtime_capability_catalog, get_runtime_provider_catalog
from app.core.db import SessionLocal, get_db
from app.models.graph_version import GraphTopologyVersionModel
from app.schemas.graph import GraphTopologyVersion, GraphTopologyVersionCreate, GraphTopologyVersionList
from app.agents.graph_registry import graph_registry
from app.api import deps

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(deps.get_current_active_user)])


@router.get("/topology")
async def get_graph_topology():
    """
    返回当前对话图的 Mermaid 表示。

    前端可直接将此字符串渲染为可视化流程图。
    """
    mermaid = await get_graph_mermaid()
    return {
        "mermaid": mermaid,
        "nodes": [
            "context",
            "task_planner",
            "agent",
            "tool_executor",
            "handoff",
            "orchestrator_invoke",
            "synthesize",
            "task_evaluator",
        ],
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
                "id": "task_planner",
                "label": "任务理解与计划",
                "description": "生成 task_frame、execution_plan 和验收标准，作为后续执行的运行时契约",
                "icon": "🧭",
                "color": "#13c2c2"
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
                "id": "orchestrator_invoke",
                "label": "子主控调用",
                "description": "按语义策略把任务委托给另一个主控应用，形成应用级编排",
                "icon": "🧩",
                "color": "#2f54eb"
            },
            {
                "id": "synthesize",
                "label": "汇总归还",
                "description": "专家完成后关闭协作区块，将控制权归还给主控智能体",
                "icon": "📝",
                "color": "#eb2f96"
            },
            {
                "id": "task_evaluator",
                "label": "任务验收与修复",
                "description": "主控结束前检查计划、产物和约束；失败时可触发一次运行时修复",
                "icon": "✅",
                "color": "#389e0d"
            }
        ]
    }


@router.get("/runtime/capabilities")
async def get_graph_runtime_capabilities():
    """
    返回 Agent Runtime 框架能力目录。

    用于前端、SDK 或平台用户理解当前内核提供哪些可组合运行能力。
    """
    return {
        "capabilities": get_runtime_capability_catalog(),
        "providers": get_runtime_provider_catalog(),
        "state_fields": [
            "task_frame",
            "execution_plan",
            "execution_artifacts",
            "task_evaluation",
            "task_repair_count",
            "pending_repair",
        ],
        "events": [
            "task_runtime",
            "task_runtime_update",
            "task_evaluation",
            "tool_runtime",
            "node_event",
        ],
        "request_config": {
            "graph_template_id": "选择运行图模板",
            "interaction_mode": "选择交互模式",
            "enable_memory": "是否启用长期记忆",
            "enable_swarm": "是否启用专家/子主控协作",
            "enable_canvas": "是否启用看板工具",
            "max_task_repairs": "验收失败后的运行时修复次数，当前建议 0-3",
        },
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
