from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, case
from typing import List, Optional, Dict, Any
from app.core.db import get_db
from app.models.audit import ActionLog
from app.models.session import ChatSession
from app.models.message import ChatMessage
from app.models.graph_execution import GraphExecution
from app.models.agent import AgentProfile
from app.services.audit_service import audit_service
from pydantic import BaseModel, field_validator
from datetime import datetime, timedelta

router = APIRouter()

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
    db: AsyncSession = Depends(get_db)
):
    """获取行动执行审计日志列表"""
    query = select(ActionLog).order_by(desc(ActionLog.created_at))
    if action_name:
        query = query.where(ActionLog.action_name == action_name)
    if user_id:
        query = query.where(ActionLog.user_id == user_id)
        
    result = await db.execute(query.limit(limit).offset(offset))
    return result.scalars().all()

@router.get("/stats")
async def get_stats(days: int = 7, db: AsyncSession = Depends(get_db)):
    """获取使用情况统计分析数据"""
    return await audit_service.get_usage_stats(db, days)


@router.get("/dashboard")
async def get_audit_dashboard(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db)
):
    """基于当前运行架构的统一审计看板数据。"""
    since = datetime.now() - timedelta(days=days)

    session_summary_q = select(
        func.count(ChatSession.id).label("total_sessions"),
        func.sum(case((ChatSession.status == "active", 1), else_=0)).label("active_sessions")
    ).where(ChatSession.created_at >= since)
    session_summary = (await db.execute(session_summary_q)).one()

    message_summary_q = select(
        func.count(ChatMessage.id).label("total_messages"),
        func.sum(case((ChatMessage.role == "user", 1), else_=0)).label("user_messages"),
        func.sum(case((ChatMessage.role == "assistant", 1), else_=0)).label("assistant_messages"),
        func.sum(ChatMessage.token_count).label("message_tokens"),
        func.sum(case((ChatMessage.feedback == "like", 1), else_=0)).label("likes"),
        func.sum(case((ChatMessage.feedback == "dislike", 1), else_=0)).label("dislikes")
    ).where(ChatMessage.created_at >= since)
    message_summary = (await db.execute(message_summary_q)).one()

    graph_summary_q = select(
        func.count(GraphExecution.id).label("total_executions"),
        func.sum(case((GraphExecution.status == "error", 1), else_=0)).label("error_count"),
        func.avg(GraphExecution.duration_ms).label("avg_duration_ms"),
        func.sum(GraphExecution.input_tokens + GraphExecution.output_tokens).label("graph_tokens"),
        func.sum(GraphExecution.tool_calls_count).label("tool_calls")
    ).where(GraphExecution.created_at >= since)
    graph_summary = (await db.execute(graph_summary_q)).one()

    daily_sessions_q = select(
        func.date(ChatSession.created_at).label("day"),
        func.count(ChatSession.id).label("sessions")
    ).where(ChatSession.created_at >= since).group_by(func.date(ChatSession.created_at)).order_by(func.date(ChatSession.created_at))

    daily_messages_q = select(
        func.date(ChatMessage.created_at).label("day"),
        func.count(ChatMessage.id).label("messages"),
        func.sum(ChatMessage.token_count).label("tokens")
    ).where(ChatMessage.created_at >= since).group_by(func.date(ChatMessage.created_at)).order_by(func.date(ChatMessage.created_at))

    daily_graph_q = select(
        func.date(GraphExecution.created_at).label("day"),
        func.count(GraphExecution.id).label("executions"),
        func.sum(GraphExecution.tool_calls_count).label("tool_calls")
    ).where(GraphExecution.created_at >= since).group_by(func.date(GraphExecution.created_at)).order_by(func.date(GraphExecution.created_at))

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
        GraphExecution.created_at >= since
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
        GraphExecution.created_at >= since
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
        GraphExecution.created_at >= since
    ).order_by(
        desc(GraphExecution.created_at)
    ).limit(50)

    daily_map: Dict[str, Dict[str, Any]] = {}
    for row in (await db.execute(daily_sessions_q)).all():
        day = str(row.day)
        daily_map.setdefault(day, {"date": day, "sessions": 0, "messages": 0, "tokens": 0, "executions": 0, "tool_calls": 0})
        daily_map[day]["sessions"] = row.sessions or 0
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

    recent_executions = []
    for row in (await db.execute(recent_executions_q)).all():
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
        })

    total_executions = graph_summary.total_executions or 0
    error_count = graph_summary.error_count or 0
    message_tokens = message_summary.message_tokens or 0
    graph_tokens = graph_summary.graph_tokens or 0

    return {
        "summary": {
            "total_sessions": session_summary.total_sessions or 0,
            "active_sessions": session_summary.active_sessions or 0,
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
        },
        "daily_activity": [daily_map[k] for k in sorted(daily_map.keys())],
        "top_agents": top_agents,
        "top_nodes": top_nodes,
        "recent_executions": recent_executions,
    }

@router.get("/actions/{log_id}", response_model=ActionLogResponse)
async def get_action_log(log_id: str, db: AsyncSession = Depends(get_db)):
    """获取单个行动日志详情"""
    log = await db.get(ActionLog, log_id)
    return log
