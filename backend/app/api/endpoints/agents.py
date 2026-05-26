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
from app.ontology.persistent_service import persistent_ontology_service
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
    agent_type: str = "general"
    runtime_policy: Dict[str, Any] = {}
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
    agent_type: Optional[str] = None
    runtime_policy: Optional[Dict[str, Any]] = None
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
    agent_type: str = "general"
    runtime_policy: Dict[str, Any] = {}
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
    agent_type: str = "general"
    runtime_policy: Dict[str, Any] = {}
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


def _infer_agent_type(data: Dict[str, Any]) -> str:
    explicit = str(data.get("agent_type") or "").strip().lower()
    if explicit:
        return explicit
    ontology_config = data.get("ontology_config") or {}
    tools = data.get("tools") or []
    if isinstance(ontology_config, dict) and ontology_config.get("enabled"):
        return "ontology"
    if data.get("role") == "orchestrator":
        return "workflow"
    if tools:
        return "tool"
    return "general"


def _normalize_runtime_policy(data: Dict[str, Any]) -> Dict[str, Any]:
    agent_type = data.get("agent_type") or _infer_agent_type(data)
    raw_policy = data.get("runtime_policy") or {}
    if not isinstance(raw_policy, dict):
        raise HTTPException(status_code=400, detail="runtime_policy 必须是对象")

    tools = data.get("tools") or []
    has_tools = bool(tools)
    has_web_search = "*" in tools or "web_search" in tools
    ontology_enabled = bool((data.get("ontology_config") or {}).get("enabled"))

    defaults_by_type: Dict[str, Dict[str, Any]] = {
        "general": {
            "allow_tools": False,
            "allow_web_search": False,
            "allow_swarm": False,
            "allow_canvas": True,
            "allow_ontology": False,
            "tool_call_mode": "none",
        },
        "tool": {
            "allow_tools": True,
            "allow_web_search": has_web_search,
            "allow_swarm": False,
            "allow_canvas": True,
            "allow_ontology": False,
            "tool_call_mode": "controlled",
        },
        "ontology": {
            "allow_tools": False,
            "allow_web_search": False,
            "allow_swarm": False,
            "allow_canvas": True,
            "allow_ontology": True,
            "tool_call_mode": "ontology_preflight",
        },
        "workflow": {
            "allow_tools": True,
            "allow_web_search": has_web_search,
            "allow_swarm": True,
            "allow_canvas": True,
            "allow_ontology": ontology_enabled,
            "tool_call_mode": "controlled",
        },
    }
    policy = {**defaults_by_type[agent_type], **raw_policy}
    for key in ["allow_tools", "allow_web_search", "allow_swarm", "allow_canvas", "allow_ontology"]:
        policy[key] = bool(policy.get(key))
    policy["tool_call_mode"] = str(policy.get("tool_call_mode") or defaults_by_type[agent_type]["tool_call_mode"])

    if agent_type == "general" and has_tools and "allow_tools" not in raw_policy:
        policy["allow_tools"] = True
        policy["tool_call_mode"] = "controlled"
    if agent_type == "tool" and has_tools:
        policy["allow_tools"] = True
    if agent_type == "ontology":
        policy["allow_ontology"] = True
        policy["allow_swarm"] = False
    if agent_type == "workflow":
        policy["allow_swarm"] = True
    if not policy["allow_tools"]:
        policy["allow_web_search"] = False
    return policy


def _runtime_policy_explanation(agent: AgentProfile) -> Dict[str, Any]:
    policy = agent.runtime_policy if isinstance(agent.runtime_policy, dict) else {}
    ontology_config = agent.ontology_config if isinstance(agent.ontology_config, dict) else {}
    tools = agent.tools or []

    items = [
        {
            "key": "allow_tools",
            "label": "工具调用",
            "enabled": bool(policy.get("allow_tools")),
            "effect": "允许模型调用已注册工具" if policy.get("allow_tools") else "即使配置了工具，运行时也会拦截工具调用",
        },
        {
            "key": "allow_web_search",
            "label": "联网检索",
            "enabled": bool(policy.get("allow_web_search")),
            "effect": "允许联网检索工具" if policy.get("allow_web_search") else "搜索类工具会被拦截或不暴露给模型",
        },
        {
            "key": "allow_swarm",
            "label": "多专家协作",
            "enabled": bool(policy.get("allow_swarm")),
            "effect": "允许主控移交给专家或子应用" if policy.get("allow_swarm") else "不会主动进行专家协作移交",
        },
        {
            "key": "allow_canvas",
            "label": "自动看板",
            "enabled": bool(policy.get("allow_canvas")),
            "effect": "允许生成看板/画布内容" if policy.get("allow_canvas") else "不会自动生成看板/画布",
        },
        {
            "key": "allow_ontology",
            "label": "本体运行",
            "enabled": bool(policy.get("allow_ontology")),
            "effect": "允许本体预处理、映射、规则和解释" if policy.get("allow_ontology") else "不会触发本体运行时",
        },
    ]
    warnings = []
    if tools and not policy.get("allow_tools"):
        warnings.append("已配置工具，但运行策略禁止工具调用。")
    if policy.get("allow_web_search") and not policy.get("allow_tools"):
        warnings.append("联网检索依赖工具调用；当前工具调用关闭。")
    if ontology_config.get("enabled") and not policy.get("allow_ontology"):
        warnings.append("已启用本体配置，但运行策略禁止本体运行。")
    if policy.get("allow_ontology") and not ontology_config.get("enabled"):
        warnings.append("运行策略允许本体，但本体配置未启用。")

    return {
        "agent_id": agent.id,
        "agent_name": agent.name,
        "agent_type": agent.agent_type or "general",
        "role": agent.role,
        "tool_call_mode": policy.get("tool_call_mode") or "none",
        "tools_count": len(tools),
        "ontology_mode": ontology_config.get("mode") or "off",
        "items": items,
        "warnings": warnings,
    }


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

    if "agent_type" in data or "tools" in data or "ontology_config" in data or "runtime_policy" in data or "role" in data:
        inferred_type = _infer_agent_type(data)
        if inferred_type not in {"general", "tool", "ontology", "workflow"}:
            raise HTTPException(status_code=400, detail="agent_type 仅支持 general、tool、ontology、workflow")
        data["agent_type"] = inferred_type

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
            if not normalized_config["space_id"] and normalized_config["mode"] == "required":
                warnings.append("本体 required 模式未指定 space_id，运行时会要求用户先配置本体空间。")
            if data.get("agent_type") == "general":
                data["agent_type"] = "ontology"
                warnings.append("已根据本体配置将智能体类型调整为 ontology。")
        data["ontology_config"] = normalized_config

    if "agent_type" in data or "runtime_policy" in data or "tools" in data or "ontology_config" in data or "role" in data:
        data["runtime_policy"] = _normalize_runtime_policy(data)
        if data["agent_type"] == "general" and data["runtime_policy"].get("allow_tools"):
            warnings.append("通用助手启用了工具策略，建议改为 tool 类型以便后续治理。")
        if data["agent_type"] == "tool" and not data["runtime_policy"].get("allow_tools"):
            warnings.append("工具助手当前关闭了工具调用，将只能进行普通推理。")
        if data["agent_type"] == "ontology" and not data["ontology_config"].get("enabled"):
            data["ontology_config"] = {
                **(data.get("ontology_config") or {}),
                "enabled": True,
                "mode": "auto",
            }
            warnings.append("本体增强助手已自动开启 ontology auto 模式。")
        if data["agent_type"] != "ontology" and (data.get("ontology_config") or {}).get("enabled") and not data["runtime_policy"].get("allow_ontology"):
            warnings.append("当前类型未允许本体运行，ontology_config 会被保存但运行时不会启用。")

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


async def _ensure_agent_ontology_space_access(
    db: AsyncSession,
    ontology_config: Dict[str, Any],
    current_user: User,
) -> None:
    if not ontology_config or not ontology_config.get("enabled") or not ontology_config.get("space_id"):
        return
    await persistent_ontology_service._ensure_space_access(
        db,
        ontology_config["space_id"],
        current_user.id,
        current_user.is_admin,
        action="read",
    )

# --- Endpoints ---

@router.post("/", response_model=AgentProfileResponse)
async def create_agent_profile(
    profile: AgentProfileCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """创建新的智能体 Profile"""
    normalized, _ = _normalize_agent_payload(profile)
    await _ensure_agent_ontology_space_access(db, normalized.get("ontology_config") or {}, current_user)
    new_profile = AgentProfile(
        id=f"agent-{uuid.uuid4().hex[:8]}",
        name=normalized["name"],
        description=normalized.get("description"),
        model_config_id=normalized["model_config_id"],
        system_prompt=normalized.get("system_prompt"),
        tools=normalized.get("tools", []),
        ontology_config=normalized.get("ontology_config", {}),
        agent_type=normalized.get("agent_type", "general"),
        runtime_policy=normalized.get("runtime_policy", {}),
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """列出所有智能体 Profile"""
    if current_user.is_admin:
        result = await db.execute(select(AgentProfile))
    else:
        result = await db.execute(
            select(AgentProfile).where(
                (AgentProfile.user_id == current_user.id) | (AgentProfile.is_public == True)  # noqa: E712
            )
        )
    return result.scalars().all()

@router.get("/{agent_id}", response_model=AgentProfileResponse)
async def get_agent_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """获取单个智能体详情"""
    profile = await db.get(AgentProfile, agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    if not current_user.is_admin and profile.user_id != current_user.id and not profile.is_public:
        raise HTTPException(status_code=403, detail="forbidden to access this agent profile")
    return profile


@router.get("/{agent_id}/runtime-policy")
async def get_agent_runtime_policy(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """读取智能体运行策略解释，供配置页、审计页和运行诊断复用。"""
    profile = await db.get(AgentProfile, agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    if not current_user.is_admin and profile.user_id != current_user.id and not profile.is_public:
        raise HTTPException(status_code=403, detail="forbidden to access this agent profile")
    return _runtime_policy_explanation(profile)

@router.put("/{agent_id}", response_model=AgentProfileResponse)
async def update_agent_profile(
    agent_id: str,
    update: AgentProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """更新智能体配置"""
    profile = await db.get(AgentProfile, agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    if not current_user.is_admin and profile.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="forbidden to update this agent profile")
    
    try:
        incoming = update.model_dump(exclude_unset=True)
        merged_payload = {
            "name": profile.name,
            "description": profile.description,
            "model_config_id": profile.model_config_id,
            "system_prompt": profile.system_prompt,
            "tools": profile.tools or [],
            "agent_type": getattr(profile, "agent_type", "general") or "general",
            "runtime_policy": getattr(profile, "runtime_policy", {}) or {},
            "ontology_config": profile.ontology_config or {},
            "role": profile.role,
            "routing_keywords": profile.routing_keywords or [],
            "handoff_strategy": profile.handoff_strategy,
            "is_public": profile.is_public,
            "is_active": profile.is_active,
        }
        merged_payload.update(incoming)
        normalized, _ = _normalize_agent_payload(merged_payload)
        await _ensure_agent_ontology_space_access(db, normalized.get("ontology_config") or {}, current_user)
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
                    "is_admin": bool(current_user.is_admin),
                },
                is_admin=current_user.is_admin,
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
                "is_admin": bool(current_user.is_admin),
            },
            is_admin=current_user.is_admin,
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
            "is_admin": bool(current_user.is_admin),
        },
        is_admin=current_user.is_admin,
    )
    content = response.choices[0].message.content if response.choices else ""
    return {
        "agent_id": agent_id,
        "agent_name": profile.name,
        "content": content,
    }
