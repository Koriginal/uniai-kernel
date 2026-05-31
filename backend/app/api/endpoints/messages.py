from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_
from app.core.db import get_db
from app.models.message import ChatMessage
from app.models.session import ChatSession
from app.models.tool_artifact import ToolArtifact
from app.models.user import User
from app.api import deps
from pydantic import BaseModel
from typing import Any, Dict, Optional, List
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


def _message_runtime_payload(message: ChatMessage) -> Dict[str, Any]:
    runtime_events = message.runtime_events or {}
    return {
        "message_id": str(message.id),
        "session_id": message.session_id,
        "agent_id": message.agent_id,
        "runtime_events": runtime_events,
        "task_runtime": runtime_events.get("task_runtime"),
        "ontology_runtime": runtime_events.get("ontology_runtime"),
        "tool_runtime_events": runtime_events.get("tool_runtime_events") or [],
    }


class MessageUpdate(BaseModel):
    content: Optional[str] = None
    feedback: Optional[str] = None


def _can_read_message_resource(message: ChatMessage, current_user: User) -> bool:
    return bool(current_user.is_admin or not message.user_id or message.user_id == current_user.id)


@router.get("/{message_id}/artifacts")
async def list_message_artifacts(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """列出单条消息关联的工具产物，只返回摘要，不返回完整 content。"""
    message = await db.get(ChatMessage, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    if not _can_read_message_resource(message, current_user):
        raise HTTPException(status_code=403, detail="Not allowed to read this message")

    result = await db.execute(
        select(ToolArtifact)
        .where(ToolArtifact.message_id == message_id)
        .order_by(ToolArtifact.created_at.asc())
    )
    artifacts = result.scalars().all()
    return {
        "message_id": message_id,
        "items": [
            {
                "id": item.id,
                "session_id": item.session_id,
                "message_id": item.message_id,
                "tool_call_id": item.tool_call_id,
                "tool_name": item.tool_name,
                "content_type": item.content_type,
                "preview": item.preview,
                "metadata": item.artifact_metadata or {},
                "size_bytes": item.size_bytes,
                "created_at": item.created_at,
            }
            for item in artifacts
        ],
    }


@router.get("/artifacts/{artifact_id}")
async def get_tool_artifact(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """读取工具产物完整内容。"""
    artifact = await db.get(ToolArtifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    message = await db.get(ChatMessage, artifact.message_id) if artifact.message_id else None
    if message and not _can_read_message_resource(message, current_user):
        raise HTTPException(status_code=403, detail="Not allowed to read this artifact")
    if not message and not current_user.is_admin and artifact.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to read this artifact")

    return {
        "id": artifact.id,
        "session_id": artifact.session_id,
        "message_id": artifact.message_id,
        "user_id": artifact.user_id,
        "agent_id": artifact.agent_id,
        "request_id": artifact.request_id,
        "tool_call_id": artifact.tool_call_id,
        "tool_name": artifact.tool_name,
        "content_type": artifact.content_type,
        "preview": artifact.preview,
        "content": artifact.content,
        "metadata": artifact.artifact_metadata or {},
        "size_bytes": artifact.size_bytes,
        "created_at": artifact.created_at,
    }


@router.get("/{message_id}/runtime-events")
async def get_message_runtime_events(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    获取单条 assistant 消息的运行轨迹快照。

    这里返回的是消息级展示快照，不重新执行本体/工具。
    用途：
    - 历史会话回放
    - 审计页按消息排障
    - 后续导出“回答依据”报告
    """
    message = await db.get(ChatMessage, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    if not current_user.is_admin and message.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to read this message")
    return _message_runtime_payload(message)


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
