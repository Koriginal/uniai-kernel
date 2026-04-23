from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_
from app.core.db import get_db
from app.models.message import ChatMessage
from app.models.session import ChatSession
from app.models.user import User
from app.api import deps
from pydantic import BaseModel
from typing import Optional, List
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class MessageUpdate(BaseModel):
    content: Optional[str] = None
    feedback: Optional[str] = None

@router.patch("/{message_id}")
async def update_message(
    message_id: str,
    update: MessageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    更新消息内容或反馈。
    """
    message = await db.get(ChatMessage, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    if not current_user.is_admin and message.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to update this message")
    
    if update.content is not None:
        message.content = update.content
    if update.feedback is not None:
        if update.feedback not in ["like", "dislike", "null", None]:
             raise HTTPException(status_code=400, detail="Invalid feedback value")
        message.feedback = None if update.feedback == "null" else update.feedback
        
    await db.commit()
    await db.refresh(message)
    return {"status": "updated", "id": message_id, "feedback": message.feedback}

@router.delete("/{message_id}")
async def delete_message(
    message_id: str,
    truncate: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    删除消息。
    如果 truncate 为 true，则删除该会话中在该消息之后产生的所有消息（用于回溯）。
    """
    message = await db.get(ChatMessage, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    if not current_user.is_admin and message.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to delete this message")
    
    session_id = message.session_id
    created_at = message.created_at

    if truncate:
        # 物理删除所有晚于该消息的记录
        stmt = delete(ChatMessage).where(
            and_(
                ChatMessage.session_id == session_id,
                ChatMessage.created_at > created_at
            )
        )
        await db.execute(stmt)
        
        # --- 核心：缓存失效 (Cache Invalidation) ---
        # 既然历史记录发生了截断，老的执行上下文 (thread_state) 必须清理
        # 否则 agent_service.py 会因为看到旧缓存而产生重复或混乱的消息
        session = await db.get(ChatSession, session_id)
        if session:
            session.thread_state = None
        
        await db.commit()
        return {"status": "truncated", "session_id": session_id}
    else:
        # 普通删除也建议更新缓存，或者根据业务逻辑决定
        # 为了稳妥，删除任意消息都重置缓存
        session = await db.get(ChatSession, session_id)
        if session:
            session.thread_state = None
            
        await db.delete(message)
        await db.commit()
        return {"status": "deleted", "id": message_id}
