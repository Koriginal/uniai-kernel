from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.core.db import get_db
from app.models.session import ChatSession
from pydantic import BaseModel
from typing import Optional, List
import uuid

# 引用 Agent app 用于清空状态
from app.api.endpoints.agent import agent_app

router = APIRouter()

class SessionCreate(BaseModel):
    title: Optional[str] = "New Chat"
    opening_remarks: Optional[str] = None
    
class SessionUpdate(BaseModel):
    title: Optional[str] = None
    opening_remarks: Optional[str] = None

@router.post("/")
async def create_session(session_in: SessionCreate, db: AsyncSession = Depends(get_db)):
    """
    新建会话。
    返回的 ID 可作为 Agent API 的 thread_id 使用。
    """
    new_session = ChatSession(
        title=session_in.title,
        opening_remarks=session_in.opening_remarks
    )
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return new_session

@router.get("/")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    """
    获取会话列表 (按更新时间倒序)。
    """
    # 简单的按时间倒序
    result = await db.execute(select(ChatSession).order_by(ChatSession.updated_at.desc()))
    return result.scalars().all()

@router.get("/{session_id}")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    获取会话详情。
    """
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

@router.patch("/{session_id}")
async def update_session(session_id: str, update: SessionUpdate, db: AsyncSession = Depends(get_db)):
    """
    更新会话基础信息 (标题、开场白)。
    """
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if update.title is not None:
        session.title = update.title
    if update.opening_remarks is not None:
        session.opening_remarks = update.opening_remarks
        
    await db.commit()
    await db.refresh(session)
    return session

@router.delete("/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    删除会话。
    """
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    await db.delete(session)
    await db.commit()
    return {"status": "deleted", "id": session_id}

@router.post("/{session_id}/clear")
async def clear_session_context(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    清空会话上下文 (聊天记录)。
    仅保留会话基础信息配置。
    """
    # 1. 验证会话存在
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # 2. 调用 LangGraph 的 checkpointer 清理逻辑
    # 注意: MemorySaver 并没有公开的 delete 方法，但我们可以通过 update_state 覆盖为空状态
    # 或者对于生产级的 PostgresSaver，有 delete 接口。
    # 这里我们演示 "Soft Clear" -> 注入空消息列表覆盖
    
    config = {"configurable": {"thread_id": session_id}}
    
    # 将 messages 重置为空列表，或仅保留 System Prompt (如果需要)
    # LangGraph 的 reducer 通常是 append 的，要从根本上清除需要 checkpointer 支持 delete
    # 演示：我们注入一个特定标记让前端知道 cleared，或者我们尝试 hack 内存
    
    # hack: MemorySaver 是 dict，直接根据 id 删
    # from app.api.v1.endpoints.agent import memory
    # if session_id in memory.storage:
    #     del memory.storage[session_id]
        
    # 更优雅的方式：更新为一个初始状态
    initial_messages = []
    # 如果有开场白，是否要重新注入？
    if session.opening_remarks:
        initial_messages.append({"role": "system", "content": session.opening_remarks})
        
    # 强行更新状态 (LangGraph 允许 values 覆盖)
    # 注意: 实际行为取决于 Graph 的定义，这里假设 update 能覆盖
    await agent_app.aupdate_state(config, {"messages": initial_messages}, as_node="agent") 
    
    return {"status": "cleared", "current_opening_remarks": session.opening_remarks}
