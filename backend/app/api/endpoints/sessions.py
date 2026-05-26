from fastapi import APIRouter, Depends, HTTPException, Body, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, or_
from app.core.db import get_db
from app.models.session import ChatSession
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from app.models.message import ChatMessage
from app.api import deps
from app.models.user import User
from app.api.endpoints.messages import _message_runtime_payload
from app.api.endpoints.audit import _content_preview, _runtime_trace_summary

router = APIRouter()


async def _claim_legacy_orphan_sessions_for_admin(db: AsyncSession, current_user: User) -> None:
    """
    兼容历史数据：
    旧版本会创建 user_id 为空的会话，导致升级后“会话消失/审计无数据”。
    对管理员账户自动认领这些孤儿会话，恢复可见性与统计口径。
    """
    if not current_user.is_admin:
        return
    await db.execute(
        update(ChatSession)
        .where(ChatSession.user_id.is_(None))
        .values(user_id=current_user.id)
    )
    await db.commit()

class SessionCreate(BaseModel):
    title: Optional[str] = "New Chat"
    opening_remarks: Optional[str] = None
    active_agent_id: Optional[str] = None
    
class SessionUpdate(BaseModel):
    title: Optional[str] = None
    opening_remarks: Optional[str] = None
    active_agent_id: Optional[str] = None

class SessionResponse(BaseModel):
    id: str
    title: Optional[str] = None
    status: Optional[str] = None
    active_agent_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

def _session_to_dict(s: ChatSession) -> dict:
    return {
        "id": s.id,
        "title": s.title,
        "status": s.status,
        "active_agent_id": s.active_agent_id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None
    }


def _format_trace_time(value: Optional[datetime]) -> str:
    if not value:
        return "-"
    return value.isoformat()


def _build_runtime_trace_item(session_id: str, message: ChatMessage) -> Optional[Dict[str, Any]]:
    runtime_events = message.runtime_events if isinstance(message.runtime_events, dict) else {}
    trace_summary = _runtime_trace_summary(runtime_events)
    has_runtime = trace_summary["has_ontology"] or trace_summary["tool_count"] > 0
    if not has_runtime:
        return None
    return {
        "message_id": message.id,
        "session_id": session_id,
        "agent_id": message.agent_id,
        "created_at": message.created_at,
        "content_preview": _content_preview(message.content),
        "summary": trace_summary,
        "ontology_runtime": runtime_events.get("ontology_runtime"),
        "tool_runtime_events": runtime_events.get("tool_runtime_events") or [],
    }


def _build_runtime_report_markdown(session: ChatSession, items: List[Dict[str, Any]], summary: Dict[str, int]) -> str:
    lines = [
        "# 会话运行轨迹报告",
        "",
        f"- 会话：{session.title or session.id}",
        f"- 会话 ID：{session.id}",
        f"- 生成时间：{datetime.utcnow().isoformat()}Z",
        f"- 回答数：{summary.get('total', 0)}",
        f"- 使用本体：{summary.get('with_ontology', 0)}",
        f"- 使用工具：{summary.get('with_tools', 0)}",
        f"- 工具拦截：{summary.get('blocked_tools', 0)}",
        f"- 工具失败：{summary.get('failed_tools', 0)}",
        "",
    ]
    if not items:
        lines.append("当前会话没有已落库的本体或工具运行轨迹。")
        return "\n".join(lines)

    for idx, item in enumerate(items, start=1):
        trace_summary = item.get("summary") or {}
        space_label = (
            trace_summary.get("ontology_space_name")
            or trace_summary.get("ontology_space_code")
            or trace_summary.get("ontology_space_id")
            or "未使用本体"
        )
        ontology_runtime = item.get("ontology_runtime") if isinstance(item.get("ontology_runtime"), dict) else {}
        lines.extend([
            f"## 回答 {idx}",
            "",
            f"- 时间：{_format_trace_time(item.get('created_at'))}",
            f"- 消息 ID：{item.get('message_id')}",
            f"- 智能体 ID：{item.get('agent_id') or '-'}",
            f"- 本体空间：{space_label}",
            f"- 本体状态：{trace_summary.get('ontology_status') or ('已触发' if trace_summary.get('has_ontology') else '未使用')}",
            f"- 触发判断：{ontology_runtime.get('trigger_reason') or '-'}",
            f"- 触发信号：{'，'.join(ontology_runtime.get('trigger_signals') or []) or '-'}",
            f"- 风险等级：{trace_summary.get('risk_level') or '未执行'}",
            (
                "- 工具："
                f"{trace_summary.get('tool_count', 0)} 次，"
                f"成功 {trace_summary.get('successful_tool_count', 0)}，"
                f"拦截 {trace_summary.get('blocked_tool_count', 0)}，"
                f"失败 {trace_summary.get('failed_tool_count', 0)}"
            ),
            f"- 回答摘要：{item.get('content_preview') or '无'}",
            "",
        ])
    return "\n".join(lines)


def _summarize_runtime_trace_items(items: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {
        "total": 0,
        "with_ontology": 0,
        "with_tools": 0,
        "blocked_tools": 0,
        "failed_tools": 0,
    }
    for item in items:
        trace_summary = item.get("summary") or {}
        summary["total"] += 1
        summary["with_ontology"] += 1 if trace_summary.get("has_ontology") else 0
        summary["with_tools"] += 1 if trace_summary.get("tool_count", 0) > 0 else 0
        summary["blocked_tools"] += int(trace_summary.get("blocked_tool_count") or 0)
        summary["failed_tools"] += int(trace_summary.get("failed_tool_count") or 0)
    return summary

@router.post("/")
async def create_session(
    session_in: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """新建会话。"""
    new_session = ChatSession(
        title=session_in.title,
        opening_remarks=session_in.opening_remarks,
        active_agent_id=session_in.active_agent_id,
        user_id=current_user.id,
        extra_metadata={"auth_source": "dashboard_jwt"},
    )
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return _session_to_dict(new_session)

@router.get("/")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """获取会话列表 (按创建时间倒序)。"""
    await _claim_legacy_orphan_sessions_for_admin(db, current_user)
    session_filter = ChatSession.user_id == current_user.id
    if current_user.is_admin:
        session_filter = or_(session_filter, ChatSession.user_id.is_(None))
    result = await db.execute(
        select(ChatSession)
        .where(session_filter)
        .order_by(ChatSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return [_session_to_dict(s) for s in sessions]


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    获取会话详情。
    """
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id and session.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not allowed to access this session")
    return _session_to_dict(session)

@router.patch("/{session_id}")
async def update_session(
    session_id: str,
    update: SessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    更新会话基础信息 (标题、开场白)。
    """
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id and session.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not allowed to update this session")
        
    if update.title is not None:
        session.title = update.title
    if update.opening_remarks is not None:
        session.opening_remarks = update.opening_remarks
        
    await db.commit()
    await db.refresh(session)
    return session

@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    删除会话。
    """
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id and session.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not allowed to delete this session")
        
    await db.delete(session)
    await db.commit()
    return {"status": "deleted", "id": session_id}

@router.post("/{session_id}/clear")
async def clear_session_context(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    清空会话上下文 (聊天记录)。
    仅保留会话基础信息配置。
    """
    # 1. 验证会话存在
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id and session.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not allowed to clear this session")
        
    # 2. 物理删除所有关联的消息记录 (Database Clear)
    await db.execute(
        delete(ChatMessage).where(ChatMessage.session_id == session_id)
    )
    
    # 3. 如果需要重置摘要或计数，也可以顺便清理会话表
    session.summary = None
    session.compression_count = 0
    
    await db.commit()
    
    return {"status": "cleared", "session_id": session_id}

@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """获取会话的历史消息记录。"""
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id and session.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not allowed to read this session")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()
    
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "timestamp": int(m.created_at.timestamp() * 1000) if m.created_at else 0,
            "agent_id": m.agent_id,
            "tool_calls": m.tool_calls or [],
            **_message_runtime_payload(m),
        }
        for m in messages
    ]


@router.get("/{session_id}/runtime-traces")
async def get_session_runtime_traces(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    获取单个会话内的回答运行轨迹。

    这个接口只读取 assistant 消息里的 runtime_events 快照，不重新执行工具。
    前端可以用它做会话回放、回答依据面板，或者后续导出审查报告。
    """
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id and session.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not allowed to read this session")

    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "assistant",
            ChatMessage.runtime_events.is_not(None),
        )
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()

    items = []
    for message in messages:
        item = _build_runtime_trace_item(session_id, message)
        if not item:
            continue
        items.append(item)

    return {
        "session_id": session_id,
        "session_title": session.title,
        "summary": _summarize_runtime_trace_items(items),
        "items": items,
    }


@router.get("/{session_id}/runtime-report")
async def export_session_runtime_report(
    session_id: str,
    format: str = Query("markdown", pattern="^(markdown|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    导出单个会话的运行轨迹报告。

    markdown 用于复制给客户或排障记录；json 用于后续审计归档、二次分析。
    """
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id and session.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not allowed to read this session")

    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "assistant",
            ChatMessage.runtime_events.is_not(None),
        )
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()
    items: List[Dict[str, Any]] = []
    for message in messages:
        item = _build_runtime_trace_item(session_id, message)
        if not item:
            continue
        items.append(item)
    summary = _summarize_runtime_trace_items(items)

    if format == "json":
        return {
            "session_id": session.id,
            "session_title": session.title,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "summary": summary,
            "items": items,
        }

    report = _build_runtime_report_markdown(session, items, summary)
    return PlainTextResponse(
        report,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="runtime-report-{session.id}.md"'},
    )
