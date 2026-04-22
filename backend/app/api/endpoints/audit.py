from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, case, update, or_
from typing import List, Optional, Dict, Any
from app.core.db import get_db
from app.models.audit import ActionLog
from app.models.session import ChatSession
from app.models.message import ChatMessage
from app.models.graph_execution import GraphExecution
from app.models.agent import AgentProfile
from app.models.user import User, UserApiKey
from app.api import deps
from app.services.audit_service import audit_service
from pydantic import BaseModel, field_validator
from datetime import datetime, timedelta, timezone

router = APIRouter()


async def _claim_legacy_orphan_sessions_for_admin(db: AsyncSession, current_user: User) -> None:
    """兼容旧数据：管理员访问审计时自动认领 user_id 为空的历史会话。"""
    if not current_user.is_admin:
        return
    await db.execute(
        update(ChatSession)
        .where(ChatSession.user_id.is_(None))
        .values(user_id=current_user.id)
    )
    await db.commit()

class ActionLogResponse(BaseModel):
    id: str
    session_id: Optional[str]
    user_id: str
    agent_id: Optional[str]
    action_name: str
    input_params: Optional[Dict[str, Any]]
    output_result: Optional[str]
    status: str
    duration_ms: float
    request_tokens: int
    response_tokens: int
    total_tokens: int
    cost: float
    created_at: datetime

    @field_validator('request_tokens', 'response_tokens', 'total_tokens', 'cost', mode='before')
    @classmethod
    def convert_none_to_zero(cls, v):
        return v or 0

    class Config:
        from_attributes = True

@router.get("/actions", response_model=List[ActionLogResponse])
async def list_action_logs(
    limit: int = Query(50, ge=1, le=100),
    offset: int = 0,
    action_name: Optional[str] = None,
    user_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """获取行动执行审计日志列表"""
    query = select(ActionLog).order_by(desc(ActionLog.created_at))
    if action_name:
        query = query.where(ActionLog.action_name == action_name)
    if user_id:
        if user_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Not allowed to query other tenants")
        query = query.where(ActionLog.user_id == user_id)
    elif not current_user.is_admin:
        query = query.where(ActionLog.user_id == current_user.id)
        
    result = await db.execute(query.limit(limit).offset(offset))
    return result.scalars().all()

@router.get("/stats")
async def get_stats(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """获取使用情况统计分析数据"""
    return await audit_service.get_usage_stats(db, days, user_id=None if current_user.is_admin else current_user.id)


@router.get("/dashboard")
async def get_audit_dashboard(
    days: int = Query(7, ge=1, le=90),
    scope: str = Query("mine", pattern="^(mine|global)$"),
    orchestrator_id: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    auth_source: Optional[str] = Query(None),
    api_key_id: Optional[str] = Query(None),
    tenant_user_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """业务绑定审计看板：支持租户/身份来源/API Key/智能体关联分析。"""
    if scope == "global" and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admin can access global scope")
    await _claim_legacy_orphan_sessions_for_admin(db, current_user)

    since = datetime.now(timezone.utc) - timedelta(days=days)

    def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    if tenant_user_id and tenant_user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admin can filter other tenants")

    session_query = select(
        ChatSession.id,
        ChatSession.user_id,
        ChatSession.active_agent_id,
        ChatSession.status,
        ChatSession.created_at,
        ChatSession.extra_metadata,
    )
    if scope == "mine":
        mine_filter = ChatSession.user_id == current_user.id
        if current_user.is_admin:
            mine_filter = or_(mine_filter, ChatSession.user_id.is_(None))
        session_query = session_query.where(mine_filter)
    elif tenant_user_id:
        session_query = session_query.where(ChatSession.user_id == tenant_user_id)
    scoped_session_rows = (await db.execute(session_query)).all()

    scoped_session_ids = [row.id for row in scoped_session_rows]
    active_window_session_ids: set[str] = set()
    if scoped_session_ids:
        active_window_session_ids.update(
            row.id for row in scoped_session_rows
            if _as_utc(row.created_at) and _as_utc(row.created_at) >= since
        )
        recent_msg_session_ids = (
            await db.execute(
                select(ChatMessage.session_id)
                .where(
                    ChatMessage.created_at >= since,
                    ChatMessage.session_id.in_(scoped_session_ids),
                )
                .distinct()
            )
        ).scalars().all()
        recent_exec_session_ids = (
            await db.execute(
                select(GraphExecution.session_id)
                .where(
                    GraphExecution.created_at >= since,
                    GraphExecution.session_id.in_(scoped_session_ids),
                )
                .distinct()
            )
        ).scalars().all()
        active_window_session_ids.update([sid for sid in recent_msg_session_ids if sid])
        active_window_session_ids.update([sid for sid in recent_exec_session_ids if sid])

    session_rows = [row for row in scoped_session_rows if row.id in active_window_session_ids]

    if orchestrator_id:
        session_rows = [row for row in session_rows if row.active_agent_id == orchestrator_id]

    if auth_source or api_key_id:
        filtered_rows = []
        for row in session_rows:
            metadata = row.extra_metadata if isinstance(row.extra_metadata, dict) else {}
            source_value = metadata.get("auth_source", "unknown")
            key_value = metadata.get("api_key_id")
            if auth_source and source_value != auth_source:
                continue
            if api_key_id and key_value != api_key_id:
                continue
            filtered_rows.append(row)
        session_rows = filtered_rows

    session_ids = [row.id for row in session_rows]
    if agent_id and session_ids:
        session_ids_with_agent = (
            await db.execute(
                select(GraphExecution.session_id)
                .where(
                    GraphExecution.session_id.in_(session_ids),
                    GraphExecution.created_at >= since,
                    GraphExecution.agent_id == agent_id,
                )
                .distinct()
            )
        ).scalars().all()
        session_ids_with_agent_set = set(session_ids_with_agent)
        session_rows = [row for row in session_rows if row.id in session_ids_with_agent_set]
        session_ids = [row.id for row in session_rows]

    active_sessions = sum(1 for row in session_rows if row.status == "active")

    daily_map: Dict[str, Dict[str, Any]] = {}
    for row in session_rows:
        created_at_utc = _as_utc(row.created_at)
        if created_at_utc and created_at_utc >= since:
            day = str(row.created_at.date())
            daily_map.setdefault(day, {"date": day, "sessions": 0, "messages": 0, "tokens": 0, "executions": 0, "tool_calls": 0})
            daily_map[day]["sessions"] += 1

    def _empty_payload():
        return {
            "scope": scope,
            "summary": {
                "total_sessions": len(session_rows),
                "active_sessions": active_sessions,
                "total_messages": 0,
                "user_messages": 0,
                "assistant_messages": 0,
                "total_executions": 0,
                "tool_calls": 0,
                "avg_duration_ms": 0.0,
                "error_rate": 0.0,
                "total_tokens": 0,
                "likes": 0,
                "dislikes": 0,
                "tenant_count": len({row.user_id for row in session_rows if row.user_id}),
                "api_key_sessions": 0,
                "external_api_ratio": 0.0,
                "orchestrator_sessions": 0,
            },
            "daily_activity": [daily_map[k] for k in sorted(daily_map.keys())],
            "top_agents": [],
            "top_nodes": [],
            "recent_executions": [],
            "binding": {
                "auth_source_breakdown": [],
                "top_api_keys": [],
                "tenant_usage": [],
            },
            "filter_options": {
                "orchestrators": [],
                "agents": [],
                "api_keys": [],
                "tenants": [],
                "auth_sources": ["dashboard_jwt", "api_key", "fallback", "unknown"],
            },
            "selection": {
                "orchestrator_id": orchestrator_id,
                "agent_id": agent_id,
                "auth_source": auth_source,
                "api_key_id": api_key_id,
                "tenant_user_id": tenant_user_id,
            },
        }

    if not session_ids:
        empty_payload = _empty_payload()
        agent_options_query = select(AgentProfile.id, AgentProfile.name, AgentProfile.role).where(AgentProfile.is_active == True)  # noqa: E712
        if not current_user.is_admin:
            agent_options_query = agent_options_query.where(AgentProfile.user_id == current_user.id)
        agent_options = (await db.execute(agent_options_query.order_by(AgentProfile.role, AgentProfile.name))).all()
        tenant_query = select(User.id, User.username, User.email).where(User.is_active == True).order_by(User.created_at.desc()).limit(50)  # noqa: E712
        if scope == "mine":
            tenant_query = tenant_query.where(User.id == current_user.id)
        tenant_rows = (await db.execute(tenant_query)).all()
        api_key_query = select(UserApiKey.id, UserApiKey.name, UserApiKey.user_id, UserApiKey.is_active).order_by(UserApiKey.created_at.desc()).limit(100)
        if scope == "mine":
            api_key_query = api_key_query.where(UserApiKey.user_id == current_user.id)
        api_key_rows = (await db.execute(api_key_query)).all()
        empty_payload["filter_options"] = {
            "orchestrators": [{"id": row.id, "name": row.name} for row in agent_options if row.role == "orchestrator"],
            "agents": [{"id": row.id, "name": row.name, "role": row.role} for row in agent_options],
            "api_keys": [{"id": row.id, "name": row.name, "user_id": row.user_id, "is_active": bool(row.is_active)} for row in api_key_rows],
            "tenants": [{"user_id": row.id, "name": row.username or row.email or row.id} for row in tenant_rows],
            "auth_sources": ["dashboard_jwt", "api_key", "fallback", "unknown"],
        }
        return empty_payload

    message_summary_q = select(
        func.count(ChatMessage.id).label("total_messages"),
        func.sum(case((ChatMessage.role == "user", 1), else_=0)).label("user_messages"),
        func.sum(case((ChatMessage.role == "assistant", 1), else_=0)).label("assistant_messages"),
        func.sum(ChatMessage.token_count).label("message_tokens"),
        func.sum(case((ChatMessage.feedback == "like", 1), else_=0)).label("likes"),
        func.sum(case((ChatMessage.feedback == "dislike", 1), else_=0)).label("dislikes")
    ).where(ChatMessage.created_at >= since).where(ChatMessage.session_id.in_(session_ids))
    message_summary = (await db.execute(message_summary_q)).one()

    graph_summary_q = select(
        func.count(GraphExecution.id).label("total_executions"),
        func.sum(case((GraphExecution.status == "error", 1), else_=0)).label("error_count"),
        func.avg(GraphExecution.duration_ms).label("avg_duration_ms"),
        func.sum(GraphExecution.input_tokens + GraphExecution.output_tokens).label("graph_tokens"),
        func.sum(GraphExecution.tool_calls_count).label("tool_calls")
    ).where(GraphExecution.created_at >= since).where(GraphExecution.session_id.in_(session_ids))
    graph_summary = (await db.execute(graph_summary_q)).one()

    daily_messages_q = select(
        func.date(ChatMessage.created_at).label("day"),
        func.count(ChatMessage.id).label("messages"),
        func.sum(ChatMessage.token_count).label("tokens")
    ).where(ChatMessage.created_at >= since).where(ChatMessage.session_id.in_(session_ids)).group_by(func.date(ChatMessage.created_at)).order_by(func.date(ChatMessage.created_at))

    daily_graph_q = select(
        func.date(GraphExecution.created_at).label("day"),
        func.count(GraphExecution.id).label("executions"),
        func.sum(GraphExecution.tool_calls_count).label("tool_calls")
    ).where(GraphExecution.created_at >= since).where(GraphExecution.session_id.in_(session_ids)).group_by(func.date(GraphExecution.created_at)).order_by(func.date(GraphExecution.created_at))

    top_agents_q = select(
        GraphExecution.agent_id,
        AgentProfile.name,
        func.count(GraphExecution.id).label("executions"),
        func.avg(GraphExecution.duration_ms).label("avg_duration_ms"),
        func.sum(case((GraphExecution.status == "success", 1), else_=0)).label("success_count"),
        func.sum(case((GraphExecution.status == "error", 1), else_=0)).label("error_count"),
        func.sum(GraphExecution.tool_calls_count).label("tool_calls")
    ).select_from(GraphExecution).outerjoin(
        AgentProfile, AgentProfile.id == GraphExecution.agent_id
    ).where(
        GraphExecution.created_at >= since,
        GraphExecution.session_id.in_(session_ids),
    ).group_by(
        GraphExecution.agent_id, AgentProfile.name
    ).order_by(
        desc("executions")
    ).limit(8)

    top_nodes_q = select(
        GraphExecution.node_name,
        func.count(GraphExecution.id).label("executions"),
        func.avg(GraphExecution.duration_ms).label("avg_duration_ms"),
        func.sum(case((GraphExecution.status == "error", 1), else_=0)).label("error_count")
    ).where(
        GraphExecution.created_at >= since,
        GraphExecution.session_id.in_(session_ids),
    ).group_by(
        GraphExecution.node_name
    ).order_by(
        desc("executions")
    ).limit(8)

    recent_executions_q = select(
        GraphExecution.id,
        GraphExecution.created_at,
        GraphExecution.session_id,
        GraphExecution.request_id,
        GraphExecution.node_name,
        GraphExecution.agent_id,
        AgentProfile.name.label("agent_name"),
        GraphExecution.status,
        GraphExecution.duration_ms,
        GraphExecution.input_tokens,
        GraphExecution.output_tokens,
        GraphExecution.tool_calls_count,
        GraphExecution.error_message
    ).select_from(GraphExecution).outerjoin(
        AgentProfile, AgentProfile.id == GraphExecution.agent_id
    ).where(
        GraphExecution.created_at >= since,
        GraphExecution.session_id.in_(session_ids),
    ).order_by(
        desc(GraphExecution.created_at)
    ).limit(50)

    for row in (await db.execute(daily_messages_q)).all():
        day = str(row.day)
        daily_map.setdefault(day, {"date": day, "sessions": 0, "messages": 0, "tokens": 0, "executions": 0, "tool_calls": 0})
        daily_map[day]["messages"] = row.messages or 0
        daily_map[day]["tokens"] = row.tokens or 0
    for row in (await db.execute(daily_graph_q)).all():
        day = str(row.day)
        daily_map.setdefault(day, {"date": day, "sessions": 0, "messages": 0, "tokens": 0, "executions": 0, "tool_calls": 0})
        daily_map[day]["executions"] = row.executions or 0
        daily_map[day]["tool_calls"] = row.tool_calls or 0

    top_agents = []
    for row in (await db.execute(top_agents_q)).all():
        executions = row.executions or 0
        top_agents.append({
            "agent_id": row.agent_id,
            "agent_name": row.name or row.agent_id or "System",
            "executions": executions,
            "avg_duration_ms": float(row.avg_duration_ms or 0),
            "success_rate": ((row.success_count or 0) / executions) if executions else 0,
            "error_count": row.error_count or 0,
            "tool_calls": row.tool_calls or 0,
        })

    top_nodes = []
    for row in (await db.execute(top_nodes_q)).all():
        top_nodes.append({
            "node_name": row.node_name,
            "executions": row.executions or 0,
            "avg_duration_ms": float(row.avg_duration_ms or 0),
            "error_count": row.error_count or 0,
        })

    session_by_id = {row.id: row for row in session_rows}
    msg_by_session_q = select(
        ChatMessage.session_id,
        func.count(ChatMessage.id).label("messages"),
        func.sum(ChatMessage.token_count).label("tokens"),
    ).where(
        ChatMessage.created_at >= since,
        ChatMessage.session_id.in_(session_ids),
    ).group_by(ChatMessage.session_id)
    exec_by_session_q = select(
        GraphExecution.session_id,
        func.count(GraphExecution.id).label("executions"),
        func.sum(GraphExecution.input_tokens + GraphExecution.output_tokens).label("tokens"),
        func.sum(GraphExecution.tool_calls_count).label("tool_calls"),
        func.sum(case((GraphExecution.status == "error", 1), else_=0)).label("errors"),
    ).where(
        GraphExecution.created_at >= since,
        GraphExecution.session_id.in_(session_ids),
    ).group_by(GraphExecution.session_id)
    msg_by_session = {row.session_id: row for row in (await db.execute(msg_by_session_q)).all()}
    exec_by_session = {row.session_id: row for row in (await db.execute(exec_by_session_q)).all()}

    tenant_agg: Dict[str, Dict[str, Any]] = {}
    api_key_agg: Dict[str, Dict[str, Any]] = {}
    auth_source_agg: Dict[str, int] = {}

    for sid in session_ids:
        srow = session_by_id[sid]
        metadata = srow.extra_metadata if isinstance(srow.extra_metadata, dict) else {}
        auth_source = metadata.get("auth_source", "unknown")
        api_key_id = metadata.get("api_key_id")
        api_key_name = metadata.get("api_key_name") or "未命名 Key"
        uid = srow.user_id or "unknown"
        msg_metrics = msg_by_session.get(sid)
        exec_metrics = exec_by_session.get(sid)

        auth_source_agg[auth_source] = auth_source_agg.get(auth_source, 0) + 1

        tenant_item = tenant_agg.setdefault(uid, {
            "user_id": uid,
            "sessions": 0,
            "messages": 0,
            "executions": 0,
            "tokens": 0,
            "tool_calls": 0,
            "errors": 0,
        })
        tenant_item["sessions"] += 1
        tenant_item["messages"] += int((msg_metrics.messages if msg_metrics else 0) or 0)
        tenant_item["executions"] += int((exec_metrics.executions if exec_metrics else 0) or 0)
        tenant_item["tokens"] += int((((msg_metrics.tokens if msg_metrics else 0) or 0) + ((exec_metrics.tokens if exec_metrics else 0) or 0)))
        tenant_item["tool_calls"] += int((exec_metrics.tool_calls if exec_metrics else 0) or 0)
        tenant_item["errors"] += int((exec_metrics.errors if exec_metrics else 0) or 0)

        if api_key_id:
            key_item = api_key_agg.setdefault(api_key_id, {
                "api_key_id": api_key_id,
                "name": api_key_name,
                "sessions": 0,
                "messages": 0,
                "executions": 0,
                "tokens": 0,
                "tool_calls": 0,
                "errors": 0,
            })
            key_item["sessions"] += 1
            key_item["messages"] += int((msg_metrics.messages if msg_metrics else 0) or 0)
            key_item["executions"] += int((exec_metrics.executions if exec_metrics else 0) or 0)
            key_item["tokens"] += int((((msg_metrics.tokens if msg_metrics else 0) or 0) + ((exec_metrics.tokens if exec_metrics else 0) or 0)))
            key_item["tool_calls"] += int((exec_metrics.tool_calls if exec_metrics else 0) or 0)
            key_item["errors"] += int((exec_metrics.errors if exec_metrics else 0) or 0)

    user_ids = [uid for uid in tenant_agg.keys() if uid != "unknown"]
    user_name_map: Dict[str, str] = {}
    if user_ids:
        user_rows = (await db.execute(select(User.id, User.username, User.email).where(User.id.in_(user_ids)))).all()
        user_name_map = {row.id: (row.username or row.email or row.id) for row in user_rows}

    api_key_ids = list(api_key_agg.keys())
    api_key_state_map: Dict[str, bool] = {}
    if api_key_ids:
        api_key_rows = (await db.execute(select(UserApiKey.id, UserApiKey.name, UserApiKey.is_active).where(UserApiKey.id.in_(api_key_ids)))).all()
        for row in api_key_rows:
            api_key_state_map[row.id] = bool(row.is_active)
            if row.id in api_key_agg and row.name:
                api_key_agg[row.id]["name"] = row.name

    recent_executions = []
    for row in (await db.execute(recent_executions_q)).all():
        sess = session_by_id.get(row.session_id)
        meta = sess.extra_metadata if sess and isinstance(sess.extra_metadata, dict) else {}
        recent_executions.append({
            "id": row.id,
            "created_at": row.created_at,
            "session_id": row.session_id,
            "request_id": row.request_id,
            "node_name": row.node_name,
            "agent_id": row.agent_id,
            "agent_name": row.agent_name or row.agent_id or "System",
            "status": row.status,
            "duration_ms": float(row.duration_ms or 0),
            "input_tokens": row.input_tokens or 0,
            "output_tokens": row.output_tokens or 0,
            "tool_calls_count": row.tool_calls_count or 0,
            "error_message": row.error_message,
            "user_id": sess.user_id if sess else None,
            "auth_source": meta.get("auth_source", "unknown"),
            "api_key_id": meta.get("api_key_id"),
        })

    total_executions = graph_summary.total_executions or 0
    error_count = graph_summary.error_count or 0
    message_tokens = message_summary.message_tokens or 0
    graph_tokens = graph_summary.graph_tokens or 0
    api_key_session_count = sum(1 for row in session_rows if isinstance(row.extra_metadata, dict) and row.extra_metadata.get("api_key_id"))
    external_api_ratio = (api_key_session_count / len(session_rows)) if session_rows else 0
    orchestrator_session_count = sum(1 for row in session_rows if row.active_agent_id)

    agent_options_query = select(AgentProfile.id, AgentProfile.name, AgentProfile.role).where(AgentProfile.is_active == True)  # noqa: E712
    if not current_user.is_admin:
        agent_options_query = agent_options_query.where(AgentProfile.user_id == current_user.id)
    agent_options = (await db.execute(agent_options_query.order_by(AgentProfile.role, AgentProfile.name))).all()

    api_key_options_query = select(UserApiKey.id, UserApiKey.name, UserApiKey.user_id, UserApiKey.is_active).order_by(UserApiKey.created_at.desc()).limit(100)
    if scope == "mine":
        api_key_options_query = api_key_options_query.where(UserApiKey.user_id == current_user.id)
    api_key_options = (await db.execute(api_key_options_query)).all()

    auth_sources = [k for k, _ in sorted(auth_source_agg.items(), key=lambda x: x[1], reverse=True)]
    for source_name in ["dashboard_jwt", "api_key", "fallback", "unknown"]:
        if source_name not in auth_sources:
            auth_sources.append(source_name)

    return {
        "scope": scope,
        "summary": {
            "total_sessions": len(session_rows),
            "active_sessions": active_sessions,
            "total_messages": message_summary.total_messages or 0,
            "user_messages": message_summary.user_messages or 0,
            "assistant_messages": message_summary.assistant_messages or 0,
            "total_executions": total_executions,
            "tool_calls": graph_summary.tool_calls or 0,
            "avg_duration_ms": float(graph_summary.avg_duration_ms or 0),
            "error_rate": (error_count / total_executions) if total_executions else 0,
            "total_tokens": message_tokens + graph_tokens,
            "likes": message_summary.likes or 0,
            "dislikes": message_summary.dislikes or 0,
            "tenant_count": len([u for u in tenant_agg.keys() if u != "unknown"]),
            "api_key_sessions": api_key_session_count,
            "external_api_ratio": external_api_ratio,
            "orchestrator_sessions": orchestrator_session_count,
        },
        "daily_activity": [daily_map[k] for k in sorted(daily_map.keys())],
        "top_agents": top_agents,
        "top_nodes": top_nodes,
        "recent_executions": recent_executions,
        "binding": {
            "auth_source_breakdown": [
                {"source": k, "sessions": v} for k, v in sorted(auth_source_agg.items(), key=lambda x: x[1], reverse=True)
            ],
            "top_api_keys": [
                {
                    **item,
                    "is_active": api_key_state_map.get(item["api_key_id"], True),
                }
                for item in sorted(api_key_agg.values(), key=lambda x: (x["executions"], x["messages"]), reverse=True)[:10]
            ],
            "tenant_usage": [
                {
                    **item,
                    "tenant_name": user_name_map.get(item["user_id"], item["user_id"]),
                }
                for item in sorted(tenant_agg.values(), key=lambda x: (x["executions"], x["messages"]), reverse=True)[:20]
            ],
        },
        "filter_options": {
            "orchestrators": [{"id": row.id, "name": row.name} for row in agent_options if row.role == "orchestrator"],
            "agents": [{"id": row.id, "name": row.name, "role": row.role} for row in agent_options],
            "api_keys": [
                {"id": row.id, "name": row.name, "user_id": row.user_id, "is_active": bool(row.is_active)}
                for row in api_key_options
            ],
            "tenants": [
                {"user_id": uid, "name": user_name_map.get(uid, uid)}
                for uid in sorted([u for u in tenant_agg.keys() if u != "unknown"])
            ],
            "auth_sources": auth_sources,
        },
        "selection": {
            "orchestrator_id": orchestrator_id,
            "agent_id": agent_id,
            "auth_source": auth_source,
            "api_key_id": api_key_id,
            "tenant_user_id": tenant_user_id,
        },
    }

@router.get("/actions/{log_id}", response_model=ActionLogResponse)
async def get_action_log(
    log_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """获取单个行动日志详情"""
    log = await db.get(ActionLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Action log not found")
    if log.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not allowed to access this action log")
    return log
