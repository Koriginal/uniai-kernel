from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, or_
from app.core.db import get_db
from app.models.session import ChatSession
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

from app.models.message import ChatMessage
from app.api import deps
from app.models.user import User

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
            "tool_calls": m.tool_calls or []
        }
        for m in messages
    ]
