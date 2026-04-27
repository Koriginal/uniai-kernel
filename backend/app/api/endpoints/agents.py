from fastapi import APIRouter, Depends, HTTPException
from starlette.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, case
from typing import List, Optional, Union, Dict, Any, Tuple
from app.core.db import get_db
from app.models.agent import AgentProfile
from app.models.openai import ChatCompletionRequest, ChatCompletionMessage
from app.services.agent_service import agent_service
from app.core.plugins import registry
from app.api import deps
from app.models.user import User
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uuid
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(deps.get_current_active_user)])

# --- Schemas ---

class AgentProfileCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_config_id: int
    system_prompt: Optional[str] = None
    tools: List[str] = []
    ontology_config: Dict[str, Any] = {}
    role: str = "expert"  # 'orchestrator' or 'expert'
    routing_keywords: List[str] = []
    handoff_strategy: str = "return" # 'return' or 'end'
    is_public: bool = False
    is_active: bool = True

class AgentProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    model_config_id: Optional[int] = None
    system_prompt: Optional[str] = None
    tools: Optional[List[str]] = None
    ontology_config: Optional[Dict[str, Any]] = None
    role: Optional[str] = None
    routing_keywords: Optional[List[str]] = None
    handoff_strategy: Optional[str] = None
    is_public: Optional[bool] = None
    is_active: Optional[bool] = None

class AgentProfileResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    model_config_id: int
    system_prompt: Optional[str] = None
    tools: List[str]
    ontology_config: Dict[str, Any] = {}
    role: str
    routing_keywords: List[str]
    handoff_strategy: str
    is_public: bool
    is_active: bool

    class Config:
        from_attributes = True

class AgentChatRequest(BaseModel):
    query: Union[str, List[Dict[str, Any]]] # 支持图片/多模态
    session_id: Optional[str] = None
    stream: bool = True
    interaction_mode: str = "chat"
    enable_memory: bool = False
    enable_swarm: bool = True
    enable_canvas: bool = True
    skip_save_user: bool = False # 控制是否重复保存用户消息


class AgentProfileValidationRequest(BaseModel):
    name: str
    description: Optional[str] = None
    model_config_id: int
    system_prompt: Optional[str] = None
    tools: List[str] = []
    ontology_config: Dict[str, Any] = {}
    role: str = "expert"
    routing_keywords: List[str] = []
    handoff_strategy: str = "return"
    is_public: bool = False
    is_active: bool = True


class AgentProfileValidationResponse(BaseModel):
    ok: bool
    normalized_payload: Dict[str, Any]
    warnings: List[str]


class AgentTestRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    interaction_mode: str = "chat"
    enable_memory: bool = False
    enable_swarm: bool = True
    enable_canvas: bool = False


def _normalize_agent_payload(payload: AgentProfileCreate | AgentProfileUpdate | AgentProfileValidationRequest) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else dict(payload)

    if "name" in data:
      name = (data.get("name") or "").strip()
      if len(name) < 2:
          raise HTTPException(status_code=400, detail="专家名称至少需要 2 个字符")
      data["name"] = name

    if "description" in data and data.get("description") is not None:
      data["description"] = data["description"].strip()

    if "role" in data and data.get("role") not in {"orchestrator", "expert"}:
        raise HTTPException(status_code=400, detail="role 仅支持 orchestrator 或 expert")

    if "handoff_strategy" in data and data.get("handoff_strategy") not in {"return", "end"}:
        raise HTTPException(status_code=400, detail="handoff_strategy 仅支持 return 或 end")

    if "tools" in data:
        available_tools = {item["name"] for item in registry.get_action_catalog()}
        unique_tools = []
        has_wildcard = False
        for tool in data.get("tools") or []:
            normalized_tool = str(tool).strip()
            if not normalized_tool:
                continue
            if normalized_tool.lower() in {"*", "all", "__all__"}:
                has_wildcard = True
                continue
            if normalized_tool not in unique_tools:
                unique_tools.append(normalized_tool)
        unknown_tools = [tool for tool in unique_tools if tool not in available_tools]
        if unknown_tools:
            raise HTTPException(status_code=400, detail=f"以下工具未在注册表中找到: {', '.join(unknown_tools)}")
        if has_wildcard:
            data["tools"] = ["*"]
            if unique_tools:
                warnings.append("检测到通配符工具配置，已按“全部工具”处理并忽略其他显式工具项。")
        else:
            data["tools"] = unique_tools
        if not has_wildcard and not unique_tools:
            warnings.append("当前专家未配置任何工具，只能进行纯文本推理。")

    if "routing_keywords" in data:
        keywords = []
        for item in data.get("routing_keywords") or []:
            normalized = str(item).strip()
            if normalized and normalized not in keywords:
                keywords.append(normalized)
        data["routing_keywords"] = keywords
        if data.get("role") == "expert" and not keywords:
            warnings.append("专家未设置路由关键词，自动路由时更难被主控命中。")
        if data.get("role") == "orchestrator" and keywords:
            warnings.append("主控不会出现在专家协作目录中，这些路由关键词不会被其他主控用于专家移交。")

    if "ontology_config" in data:
        raw_config = data.get("ontology_config") or {}
        if not isinstance(raw_config, dict):
            raise HTTPException(status_code=400, detail="ontology_config 必须是对象")
        mode = str(raw_config.get("mode") or ("auto" if raw_config.get("enabled") else "off")).lower()
        if mode not in {"off", "auto", "required"}:
            raise HTTPException(status_code=400, detail="ontology_config.mode 仅支持 off、auto、required")
        normalized_config = {
            "enabled": mode != "off",
            "mode": mode,
            "space_id": (raw_config.get("space_id") or "").strip() or None,
            "strict_rules": bool(raw_config.get("strict_rules", False)),
            "explain_required": bool(raw_config.get("explain_required", True)),
            "fallback_when_unavailable": raw_config.get("fallback_when_unavailable") or "continue_without_ontology",
        }
        if normalized_config["enabled"]:
            ontology_tools = {
                "ontology_list_spaces",
                "ontology_get_runtime_contract",
                "ontology_map_input",
                "ontology_evaluate_rules",
                "ontology_explain_decision",
            }
            configured_tools = set(data.get("tools") or [])
            if "*" not in configured_tools:
                data["tools"] = sorted(configured_tools | ontology_tools)
            if not normalized_config["space_id"] and normalized_config["mode"] == "required":
                warnings.append("本体 required 模式未指定 space_id，运行时会要求用户先配置本体空间。")
        data["ontology_config"] = normalized_config

    if "system_prompt" in data and data.get("system_prompt"):
        prompt = data["system_prompt"].strip()
        data["system_prompt"] = prompt
        if len(prompt) < 20:
            warnings.append("系统指令较短，建议明确职责、边界和输出风格。")

    if data.get("role") == "orchestrator" and data.get("handoff_strategy") == "end":
        warnings.append("主控通常建议使用 return，以便在多专家协作后继续汇总回复。")

    if data.get("role") == "orchestrator":
        warnings.append("当前主控不会再作为 transfer_to_agent 的专家目标；它会以子应用的形式出现在主控应用目录中。")

    return data, warnings

# --- Endpoints ---

@router.post("/", response_model=AgentProfileResponse)
async def create_agent_profile(
    profile: AgentProfileCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """创建新的智能体 Profile"""
    normalized, _ = _normalize_agent_payload(profile)
    new_profile = AgentProfile(
        id=f"agent-{uuid.uuid4().hex[:8]}",
        name=normalized["name"],
        description=normalized.get("description"),
        model_config_id=normalized["model_config_id"],
        system_prompt=normalized.get("system_prompt"),
        tools=normalized.get("tools", []),
        ontology_config=normalized.get("ontology_config", {}),
        role=normalized.get("role", "expert"),
        routing_keywords=normalized.get("routing_keywords", []),
        handoff_strategy=normalized.get("handoff_strategy", "return"),
        is_public=normalized.get("is_public", False),
        is_active=normalized.get("is_active", True),
        user_id=current_user.id
    )
    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)
    return new_profile

@router.get("/", response_model=List[AgentProfileResponse])
async def list_agent_profiles(
    db: AsyncSession = Depends(get_db)
):
    """列出所有智能体 Profile"""
    result = await db.execute(select(AgentProfile))
    return result.scalars().all()

@router.get("/{agent_id}", response_model=AgentProfileResponse)
async def get_agent_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取单个智能体详情"""
    profile = await db.get(AgentProfile, agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    return profile

@router.put("/{agent_id}", response_model=AgentProfileResponse)
async def update_agent_profile(
    agent_id: str,
    update: AgentProfileUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新智能体配置"""
    profile = await db.get(AgentProfile, agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    
    try:
        normalized, _ = _normalize_agent_payload(update)
        for field, value in normalized.items():
            setattr(profile, field, value)
        
        await db.commit()
        await db.refresh(profile)
        return profile
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Error updating agent {agent_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")


@router.post("/validate", response_model=AgentProfileValidationResponse)
async def validate_agent_profile(payload: AgentProfileValidationRequest):
    """创建/编辑前校验专家配置，供前端预检使用。"""
    normalized, warnings = _normalize_agent_payload(payload)
    return {
        "ok": True,
        "normalized_payload": normalized,
        "warnings": warnings,
    }


@router.get("/dashboard/summary")
async def get_agent_dashboard(db: AsyncSession = Depends(get_db)):
    """专家管理页概览数据。"""
    from app.models.agent_score import AgentScoreHistory
    from app.models.graph_execution import GraphExecution

    result = await db.execute(select(AgentProfile))
    agents = result.scalars().all()

    stats_result = await db.execute(
        select(
            GraphExecution.agent_id,
            func.count(GraphExecution.id).label("runs"),
            func.avg(GraphExecution.duration_ms).label("avg_duration_ms"),
            func.sum(case((GraphExecution.status == "success", 1), else_=0)).label("success_count"),
            func.sum(case((GraphExecution.status == "error", 1), else_=0)).label("error_count"),
            func.max(GraphExecution.created_at).label("last_run_at"),
        )
        .where(GraphExecution.agent_id.is_not(None))
        .group_by(GraphExecution.agent_id)
    )
    graph_stats = {row.agent_id: row for row in stats_result.all()}

    latest_score_result = await db.execute(
        select(AgentScoreHistory)
        .order_by(AgentScoreHistory.agent_id, desc(AgentScoreHistory.computed_at))
    )
    latest_scores: Dict[str, Any] = {}
    for item in latest_score_result.scalars().all():
        if item.agent_id not in latest_scores:
            latest_scores[item.agent_id] = item

    dashboard_agents = []
    for agent in agents:
        run_stats = graph_stats.get(agent.id)
        score = latest_scores.get(agent.id)
        runs = int(run_stats.runs) if run_stats and run_stats.runs else 0
        success_rate = (
            float(run_stats.success_count or 0) / runs
            if run_stats and runs
            else float(score.success_rate) if score else 0.0
        )
        dashboard_agents.append({
            "id": agent.id,
            "name": agent.name,
            "role": agent.role,
            "is_active": agent.is_active,
            "is_public": agent.is_public,
            "tools_count": len(agent.tools or []),
            "routing_keywords_count": len(agent.routing_keywords or []),
            "runs": runs,
            "success_rate": success_rate,
            "avg_duration_ms": float(run_stats.avg_duration_ms or 0) if run_stats else float(score.avg_duration_ms or 0) if score else 0.0,
            "error_count": int(run_stats.error_count or 0) if run_stats else 0,
            "last_run_at": run_stats.last_run_at if run_stats else None,
        })

    return {
        "summary": {
            "total": len(agents),
            "active": sum(1 for a in agents if a.is_active),
            "orchestrators": sum(1 for a in agents if a.role == "orchestrator"),
            "experts": sum(1 for a in agents if a.role == "expert"),
            "public_count": sum(1 for a in agents if a.is_public),
        },
        "agents": dashboard_agents,
    }

@router.get("/{agent_id}/stats")
async def get_agent_stats(
    agent_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取智能体的执行统计指标 (评分卡)"""
    from app.models.agent_score import AgentScoreHistory
    # 获取最新的评分记录
    stmt = (
        select(AgentScoreHistory)
        .where(AgentScoreHistory.agent_id == agent_id)
        .order_by(AgentScoreHistory.computed_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    score = result.scalar_one_or_none()
    
    if not score:
        return {
            "total_calls": 0,
            "success_rate": 0,
            "avg_duration_ms": 0,
            "avg_quality_score": 0
        }
    
    return {
        "total_calls": score.total_calls,
        "success_rate": score.success_rate,
        "avg_duration_ms": score.avg_duration_ms,
        "avg_quality_score": score.avg_quality_score
    }

@router.delete("/{agent_id}")
async def delete_agent_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db)
):
    """删除智能体"""
    profile = await db.get(AgentProfile, agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    
    await db.delete(profile)
    await db.commit()
    return {"status": "deleted"}

@router.post("/{agent_id}/chat")
async def agent_chat(
    agent_id: str,
    request_data: AgentChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    智能体业务对话专线：
    采用极简 Schema，自动封装为 OpenAI 协议并由 AgentService 执行。
    """
    profile = await db.get(AgentProfile, agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found")
        
    # 使用鉴权用户身份，避免回退到历史默认值导致会话归属错乱
    user_id = current_user.id

    # 模拟构造一个标准 OpenAI 请求体
    openai_request = ChatCompletionRequest(
        model=agent_id,
        messages=[
            ChatCompletionMessage(role="user", content=request_data.query)
        ],
        stream=request_data.stream,
        interaction_mode=request_data.interaction_mode,
        skip_save_user=request_data.skip_save_user
    )
    
    if request_data.stream:
        return StreamingResponse(
            agent_service.chat_stream(
                request=openai_request,
                user_id=user_id,
                session_id=request_data.session_id,
                enable_memory=request_data.enable_memory,
                enable_swarm=request_data.enable_swarm,
                enable_canvas=request_data.enable_canvas,
                skip_save_user=request_data.skip_save_user,
                identity_context={
                    "source": "dashboard_jwt",
                    "user_id": current_user.id,
                },
            ),
            media_type="text/event-stream"
        )
    else:
        # 统一使用业务层方法接入
        return await agent_service.chat(
            request=openai_request,
            user_id=user_id,
            session_id=request_data.session_id,
            enable_memory=request_data.enable_memory,
            enable_swarm=request_data.enable_swarm,
            enable_canvas=request_data.enable_canvas,
            identity_context={
                "source": "dashboard_jwt",
                "user_id": current_user.id,
            },
        )


@router.post("/{agent_id}/test")
async def test_agent_profile(
    agent_id: str,
    request_data: AgentTestRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """快速试跑指定专家配置，验证当前配置是否可正常响应。"""
    profile = await db.get(AgentProfile, agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found")

    user_id = current_user.id
    response = await agent_service.chat(
        request=ChatCompletionRequest(
            model=agent_id,
            messages=[ChatCompletionMessage(role="user", content=request_data.query)],
            stream=False,
            interaction_mode=request_data.interaction_mode,
        ),
        user_id=user_id,
        session_id=request_data.session_id,
        enable_memory=request_data.enable_memory,
        enable_swarm=request_data.enable_swarm,
        enable_canvas=request_data.enable_canvas,
        identity_context={
            "source": "dashboard_jwt",
            "user_id": current_user.id,
        },
    )
    content = response.choices[0].message.content if response.choices else ""
    return {
        "agent_id": agent_id,
        "agent_name": profile.name,
        "content": content,
    }
