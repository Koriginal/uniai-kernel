from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from app.core.db import get_db
from app.core.config import settings
from app.services.context_service import context_service
from app.services.memory_service import memory_service
from app.models.message import ChatMessage
from app.core.llm import completion
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    message: str
    enable_memory: bool = True
    enable_session_context: bool = True

async def chat_stream_generator(
    request: ChatRequest,
    db: AsyncSession
):
    """
    流式对话生成器（SSE 格式）。
    """
    try:
        # 1. 发送状态
        yield f"data: {json.dumps({'type': 'status', 'content': '正在检索记忆...'}, ensure_ascii=False)}\n\n"
        
        # 2. 构建上下文
        messages = await context_service.build_context_messages(
            session_id=request.session_id,
            user_id=request.user_id,
            current_query=request.message,
            db_session=db,
            enable_memory=request.enable_memory,
            enable_session_summary=request.enable_session_context  # 映射到正确的参数名
        )
        
        # 3. 发送思考过程
        if request.enable_memory:
            yield f"data: {json.dumps({'type': 'thought', 'content': '已加载用户偏好和历史记忆'}, ensure_ascii=False)}\n\n"
        
        yield f"data: {json.dumps({'type': 'status', 'content': '正在生成回答...'}, ensure_ascii=False)}\n\n"
        
        # 4. 流式生成
        response = await completion(
            messages=messages,
            user_id=request.user_id,
            stream=True
        )
        full_answer = ""
        
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_answer += token
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
        
        # 5. 保存消息
        user_msg = ChatMessage(
            session_id=request.session_id,
            role="user",
            content=request.message,
            user_id=request.user_id,
            token_count=len(request.message)  # 简化计算
        )
        ai_msg = ChatMessage(
            session_id=request.session_id,
            role="assistant",
            content=full_answer,
            user_id=request.user_id,
            token_count=len(full_answer)  # 简化计算
        )
        db.add(user_msg)
        db.add(ai_msg)
        await db.commit()
        
        # 6. 后台任务（记忆提取 + 会话压缩）
        # 注意：这里简化处理，直接调用，实际应该用 FastAPI BackgroundTasks
        if settings.MEMORY_EXTRACTION_ENABLED:
            try:
                # 重新获取 session 避免 session 关闭问题
                async with db.begin():
                    await memory_service.extract_memories(
                        db, request.user_id, request.message, full_answer
                    )
                    
                    # 检查是否需要压缩
                    await context_service.compress_session(
                        request.session_id, db
                    )
            except Exception as e:
                logger.warning(f"Background tasks failed: {e}")
        
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"Chat stream error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

@router.post("/")
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    智能对话接口（流式响应，SSE 格式）。
    
    自动加载：
    - 用户长期记忆（基于语义检索）
    - 会话摘要（滚动压缩的历史）
    
    响应格式（Server-Sent Events）:
    - `{"type": "status", "content": "..."}` - 状态更新
    - `{"type": "thought", "content": "..."}` - 思考过程
    - `{"type": "token", "content": "..."}` - 生成的 token
    - `[DONE]` - 流结束标记
    """
    return StreamingResponse(
        chat_stream_generator(request, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用 nginx 缓冲
        }
    )
