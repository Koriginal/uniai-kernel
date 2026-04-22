from typing import List, Dict, Any, Optional, Union
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from app.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatCompletionMessage,
    ChatCompletionUsage,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta
)
from app.core.llm import completion
from app.core.plugins import registry
from app.services.context_service import context_service
from app.models.message import ChatMessage
from app.models.agent import AgentProfile
from app.models.audit import ActionLog
from app.models.provider import UserModelConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.models.session import ChatSession
from app.api import deps
import time
import json
import uuid
import logging
from app.services.agent_service import agent_service

logger = logging.getLogger(__name__)

router = APIRouter()

# _clean_messages 已迁移至 app.core.llm

async def generate_sse_stream(
    request: ChatCompletionRequest, 
    req_id: str,
    session_id: str = None,
    user_id: str = None,
    enable_memory: bool = False,
    identity_context: Optional[Dict[str, Any]] = None,
):
    """
    Data Plane 流式包装器：完全托管给 AgentService 处理核心逻辑。
    """
    async for chunk in agent_service.chat_stream(
        request=request,
        user_id=user_id,
        session_id=session_id,
        enable_memory=enable_memory,
        req_id=req_id,
        identity_context=identity_context,
    ):
        yield chunk

@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    user_id: str = Depends(deps.get_identity),
    http_request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    100% 兼容 OpenAI 格式的标准对话网关。
    """
    req_id = f"chatcmpl-{uuid.uuid4().hex}"
    session_id = http_request.headers.get("X-Session-Id")
    enable_memory = http_request.headers.get("X-Enable-Memory", "false").lower() == "true"
    identity_context = getattr(http_request.state, "identity_context", None) if http_request else None
    
    if request.stream:
        return StreamingResponse(
            generate_sse_stream(
                request=request, req_id=req_id, 
                session_id=session_id, user_id=user_id, enable_memory=enable_memory,
                identity_context=identity_context,
            ),
            media_type="text/event-stream"
        )
    
    # 非流式：统一委托给 AgentService 处理
    return await agent_service.chat(
        request=request,
        user_id=user_id,
        session_id=session_id,
        enable_memory=enable_memory
        ,
        identity_context=identity_context,
    )
