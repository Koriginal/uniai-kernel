"""
UniAI Kernel — 智能体服务层（图引擎版）

AgentService 的职责已从"手写对话循环"转变为"图引擎的配置者与调度者"。
核心对话逻辑由 LangGraph StateGraph 负责，此文件仅做：
  1. 请求解析与初始化图状态
  2. 调用已编译的图（build_conversation_graph）
  3. 从 StreamCallback 读取事件并 yield SSE 到前端
  4. 全局收尾（checkpoint 持久化、finish 事件）

SSE 输出格式与原版完全一致，前端无需任何改动。
"""
from typing import List, Dict, Any, Optional, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
import logging
import uuid
import asyncio

from app.models.openai import (
    ChatCompletionRequest, ChatCompletionChunk, ChatCompletionChunkChoice,
    ChatCompletionChunkDelta, ChatCompletionResponse, ChatCompletionResponseChoice,
    ChatCompletionMessage, ChatCompletionUsage
)
from app.core.llm import _clean_messages, get_provider_config
from app.models.message import ChatMessage
from app.models.agent import AgentProfile
from app.models.session import ChatSession
from app.models.provider import UserModelConfig, ProviderModel, UserProvider
from app.services.swarm_service import swarm_service
from app.core.config import settings
from app.core.db import SessionLocal
from app.agents.graph_builder import build_conversation_graph
from app.agents.graph_registry import graph_registry
from app.agents.stream_callback import StreamCallback

logger = logging.getLogger(__name__)


class AgentService:
    """
    智能体业务服务（图引擎调度层）

    核心改变：
    - 原 528 行 while 循环 → 现在由 LangGraph StateGraph 管理
    - 此类仅负责「编排图的执行」，不再手写任何状态转换逻辑
    """

    def __init__(self):
        # 预编译图在 chat_stream 中异步初始化
        pass

    async def chat_stream(
        self,
        request: ChatCompletionRequest,
        user_id: str,
        session_id: Optional[str] = None,
        enable_memory: bool = False,
        enable_swarm: bool = True,
        enable_canvas: bool = True,
        req_id: Optional[str] = None,
        skip_save_user: bool = False,
        identity_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        驱动对话图执行，将图内部的 SSE 事件流式转发到调用方。

        图的实际执行（工具调用、专家切换、Canvas 回响等）
        全部在 agents/nodes/ 中的各节点函数内完成。
        """
        async with SessionLocal() as db:
            if not req_id:
                req_id = f"chatcmpl-{uuid.uuid4().hex}"

            # ── 1. 解析当前请求 ──
            original_msgs = [msg.model_dump(exclude_none=True) for msg in request.messages]
            internal_messages = _clean_messages(original_msgs)

            current_query = ""
            for msg in reversed(internal_messages):
                if msg.get("role") == "user":
                    content = msg.get("content")
                    if isinstance(content, list):
                        current_query = next(
                            (item.get("text", "") for item in content if item.get("type") == "text"), ""
                        )
                    else:
                        current_query = str(content)
                    break

            # ── 2. 加载当前活跃 Agent Profile ──
            agent_profile = await swarm_service.get_active_agent_profile(db, session_id, request.model)
            agent_id = agent_profile.id if agent_profile else "agent-default"

            agent_profile_dict = None
            if agent_profile:
                agent_profile_dict = {
                    "id": agent_profile.id,
                    "name": agent_profile.name,
                    "description": agent_profile.description,
                    "system_prompt": agent_profile.system_prompt,
                    "tools": agent_profile.tools or [],
                    "model_config_id": agent_profile.model_config_id,
                    "is_public": agent_profile.is_public,
                    "role": agent_profile.role,
                    "routing_keywords": agent_profile.routing_keywords or [],
                    "handoff_strategy": agent_profile.handoff_strategy,
                    "runtime_mode": "root_orchestrator" if agent_profile.role == "orchestrator" else "expert",
                }

            # ── 3. 加载专家目录（用于 System Prompt 注入） ──
            expert_prompt_catalog = ""
            orchestrator_prompt_catalog = ""
            if enable_swarm:
                expert_prompt_catalog = await swarm_service.get_expert_directory(db, user_id, agent_id)
                orchestrator_prompt_catalog = await swarm_service.get_orchestrator_directory(db, user_id, agent_id)

            # ── 4. 确保会话存在 ──
            if session_id:
                await self._ensure_session_exists(
                    db, session_id, user_id, active_agent_id=agent_id,
                    identity_context=identity_context
                )

            # ── 5. 构建流式回调桥接器 ──
            callback = StreamCallback()

            # ── 6. 构建图初始状态 ──
            initial_state = {
                "messages": internal_messages,
                "iteration_count": 0,
                "pending_tool_calls": [],
                "has_pending_handoff": False,
                "handoff_target_id": None,
                "current_agent_id": agent_id,
                "current_agent_profile": agent_profile_dict,
                "called_expert_ids": [],
                "wrapping_expert_id": None,
                "total_assistant_content": "",
                "current_msg_id": None,
                "total_tool_calls_list": [],
                "global_tool_index_offset": 0,
                "iter_text": "",
                "interaction_mode": request.interaction_mode or "chat",
                "semantic_frame": None,
                "semantic_slots": {},
                "pending_delegate_type": None,
                "recovery_count": 0,
                "last_healthy_node": None,
                "execution_trace": [],
            }

            # ── 7. 图执行配置（不可变上下文） ──
            graph_config = {
                "configurable": {
                    "thread_id": session_id or req_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "request_id": req_id,
                    "model_name": request.model,
                    "orchestrator_agent_id": agent_id,
                    "orchestrator_agent_profile": agent_profile_dict,
                    "enable_canvas": enable_canvas,
                    "enable_swarm": enable_swarm,
                    "enable_memory": enable_memory,
                    "max_iterations": settings.MAX_AGENT_ITERATIONS,
                    "expert_prompt_catalog": expert_prompt_catalog,
                    "orchestrator_prompt_catalog": orchestrator_prompt_catalog,
                    "stream_callback": callback,
                    "skip_save_user": skip_save_user,
                    "db": db,
                }
            }

            # ── 8. 异步启动图执行（后台任务） ──
            async def _run_graph():
                try:
                    # 优先根据请求中的 template_id 获取动态图，否则回退到标准图
                    template_id = request.graph_template_id or "standard"
                    graph = await graph_registry.get_compiled_graph(template_id)
                    await graph.ainvoke(initial_state, graph_config)
                    # ── 图执行成功结束后，在关闭前发送 DONE 标记 ──
                    await callback.emit("data: [DONE]\n\n")
                    logger.info(f"[AgentService] Graph execution finished for session {session_id}")
                except Exception as e:
                    logger.error(f"[AgentService] Graph execution failed: {e}")
                    err_chunk = ChatCompletionChunk(
                        id=req_id, model=request.model,
                        choices=[ChatCompletionChunkChoice(
                            index=0, delta=ChatCompletionChunkDelta(content=f"\n❌ 内核严重故障: {str(e)}")
                        )]
                    ).model_dump_json(exclude_none=True)
                    await callback.emit(f"data: {err_chunk}\n\n")
                finally:
                    await callback.close()

            graph_task = asyncio.create_task(_run_graph())

            # ── 9. 从回调队列读取并转发 SSE ──
            try:
                async for event in callback.iter_events():
                    yield event
            except Exception as e:
                logger.error(f"[AgentService] SSE forwarding failed: {e}")
            finally:
                if not graph_task.done():
                    graph_task.cancel()
                    try:
                        await graph_task
                    except asyncio.CancelledError:
                        pass

            # ── 10. 最终收尾事件 (仅发送 final_chunk，DONE 已由 _run_graph 发送) ──
            final_chunk = ChatCompletionChunk(
                id=req_id, model=request.model,
                choices=[ChatCompletionChunkChoice(
                    index=0, delta=ChatCompletionChunkDelta(), finish_reason="stop"
                )]
            ).model_dump_json(exclude_none=True)
            yield f"data: {final_chunk}\n\n"
            yield "data: [DONE]\n\n"

            # ── 11. 全局 checkpoint 持久化（图完成后） ──
            if session_id:
                try:
                    await db.commit()
                except Exception as e:
                    logger.error(f"[AgentService] Final commit failed: {e}")

    async def _ensure_session_exists(
        self, db: AsyncSession, session_id: str, user_id: str,
        title: str = "New Chat", active_agent_id: str = None,
        identity_context: Optional[Dict[str, Any]] = None,
    ):
        """确保数据库中存在对应会话记录"""
        if not session_id or not db:
            return
        result = await db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            logger.info(f"[AgentService] Auto-creating missing session: {session_id}")
            metadata = {
                "auth_source": (identity_context or {}).get("source", "unknown"),
                "api_key_id": (identity_context or {}).get("api_key_id"),
                "api_key_name": (identity_context or {}).get("api_key_name"),
            }
            session = ChatSession(
                id=session_id, user_id=user_id,
                title=title, active_agent_id=active_agent_id,
                extra_metadata=metadata,
            )
            db.add(session)
            await db.commit()
        else:
            metadata = dict(session.extra_metadata or {})
            if identity_context:
                metadata.setdefault("auth_source", identity_context.get("source", "unknown"))
                if identity_context.get("api_key_id"):
                    metadata["api_key_id"] = identity_context.get("api_key_id")
                    metadata["api_key_name"] = identity_context.get("api_key_name")
                if metadata != (session.extra_metadata or {}):
                    session.extra_metadata = metadata
                    db.add(session)
                    await db.commit()
        return session

    async def chat(
        self,
        request: ChatCompletionRequest,
        user_id: str,
        session_id: Optional[str] = None,
        enable_memory: bool = False,
        enable_swarm: bool = True,
        enable_canvas: bool = True,
        identity_context: Optional[Dict[str, Any]] = None,
    ) -> ChatCompletionResponse:
        """非流式接口：收集所有 SSE chunk 后返回完整响应"""
        full_content = ""
        req_id = f"chatcmpl-{uuid.uuid4().hex}"
        async for chunk in self.chat_stream(
            request=request, user_id=user_id, session_id=session_id,
            enable_memory=enable_memory, enable_swarm=enable_swarm,
            enable_canvas=enable_canvas, req_id=req_id,
            identity_context=identity_context,
        ):
            if isinstance(chunk, str) and chunk.startswith("data: "):
                try:
                    if "[DONE]" in chunk:
                        continue
                    data = json.loads(chunk.replace("data: ", "").strip())
                    if data.get("type") == "metadata":
                        continue
                    choice = data["choices"][0]
                    if "delta" in choice:
                        full_content += choice["delta"].get("content") or ""
                except Exception:
                    continue
        return ChatCompletionResponse(
            id=req_id, model=request.model,
            choices=[ChatCompletionResponseChoice(
                index=0,
                message=ChatCompletionMessage(role="assistant", content=full_content)
            )],
            usage=ChatCompletionUsage()
        )


agent_service = AgentService()
