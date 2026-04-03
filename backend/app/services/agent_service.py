from typing import List, Dict, Any, Optional, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
import logging
import uuid
import time
import asyncio

from app.models.openai import (
    ChatCompletionRequest, ChatCompletionChunk, ChatCompletionChunkChoice, 
    ChatCompletionChunkDelta, ChatCompletionResponse, ChatCompletionResponseChoice, 
    ChatCompletionMessage, ChatCompletionUsage
)
from app.core.llm import completion, _clean_messages, get_provider_config
from app.core.plugins import registry
from app.models.message import ChatMessage
from app.models.agent import AgentProfile
from app.models.audit import ActionLog
from app.models.session import ChatSession
from app.models.provider import UserModelConfig, ProviderModel, UserProvider
from app.services.context_service import context_service
from app.services.memory_service import memory_service
from app.services.swarm_service import swarm_service
from app.core.config import settings

logger = logging.getLogger(__name__)

class AgentService:
    """
    智能体核心业务引擎 - Swarm 6.0 主官委托制
    负责处理对话流、后台专家请教逻辑、上下文管理与视觉兼容。
    """

    async def _ensure_session_exists(self, db: AsyncSession, session_id: str, user_id: str, title: str = "New Chat"):
        if not session_id or not db:
            return
        result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
        session = result.scalar_one_or_none()
        if not session:
            logger.info(f"[AgentService] Auto-creating missing session: {session_id}")
            session = ChatSession(id=session_id, user_id=user_id, title=title)
            db.add(session)
            await db.commit()
        return session

    async def _save_checkpoint(self, db: AsyncSession, session_id: str, messages: List[Dict[str, Any]], status: str = "active", metadata: Dict = None):
        if not session_id or not db:
            return
        
        async def _perform_save():
            try:
                session = await db.get(ChatSession, session_id)
                if session:
                    state = {"messages": messages}
                    if metadata:
                        state.update(metadata)
                    elif session.thread_state:
                        if "agent_id" in session.thread_state:
                            state["agent_id"] = session.thread_state["agent_id"]
                    
                    session.thread_state = state
                    session.status = status
                    db.add(session)
                    await db.commit()
            except Exception as e:
                logger.error(f"[AgentService] Checkpoint save failed: {e}")

        await asyncio.shield(_perform_save())

    async def chat_stream(
        self,
        request: ChatCompletionRequest,
        db: AsyncSession,
        user_id: str,
        session_id: Optional[str] = None,
        enable_memory: bool = False,
        enable_swarm: bool = True,
        req_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        if not req_id:
            req_id = f"chatcmpl-{uuid.uuid4().hex}"

        # 1. 消息清洗与预处理
        internal_messages = _clean_messages([msg.model_dump(exclude_none=True) for msg in request.messages])
        
        # 2. 识别主官 Agent (首选专家)
        agent_profile = await swarm_service.get_active_agent_profile(db, session_id, request.model)
        agent_id = agent_profile.id if agent_profile else "agent-orchestrator"

        # 3. 提取用户原始 Query
        current_query = ""
        for msg in reversed(internal_messages):
            if msg.get("role") == "user":
                content = msg.get("content")
                if isinstance(content, list):
                    current_query = next((item.get("text", "") for item in content if item.get("type") == "text"), "")
                else:
                    current_query = str(content)
                break

        # 4. 会话恢复与冷启动
        if session_id:
            can_resume = False
            session = await db.get(ChatSession, session_id)
            if session and session.thread_state and "messages" in session.thread_state:
                # 检查主官是否变更
                if session.thread_state.get("agent_id") == agent_id:
                    can_resume = True

            if can_resume:
                messages_raw = session.thread_state.get("messages", [])
                internal_messages = _clean_messages(messages_raw)
                internal_messages.append({"role": "user", "content": current_query})
            else:
                await self._save_checkpoint(db, session_id, internal_messages, status="running", metadata={"agent_id": agent_id})
                db.add(ChatMessage(session_id=session_id, role="user", content=current_query))
                await db.commit()
                
                # 构建主官上下文
                internal_messages = await context_service.build_context_messages(
                    session_id=session_id, user_id=user_id, current_query=current_query,
                    db_session=db, max_tokens=4096, enable_memory=enable_memory
                )

            # 系统提示词注入
            has_system = any(m.get("role") == "system" for m in internal_messages)
            expert_prompt = ""
            if enable_swarm:
                expert_prompt = await swarm_service.get_all_experts_prompt(db, user_id, agent_id)

            if not has_system and agent_profile and agent_profile.system_prompt:
                sys_content = (expert_prompt + "\n\n" + agent_profile.system_prompt).strip()
                internal_messages.insert(0, {"role": "system", "content": sys_content})
            elif has_system:
                for m in internal_messages:
                    if m.get("role") == "system":
                        m["content"] = (expert_prompt + "\n\n" + m.get("content", "").replace("你是一个有用的 AI 助手。", "")).strip()
                        break

        # --- 6. Swarm 6.4 执行引擎 (熔断与心跳加强版) ---
        max_iterations = 8
        current_iter = 0
        called_expert_ids = set()
        total_assistant_content = ""
        
        try:
            while current_iter < max_iterations:
                current_iter += 1
                # 物理心跳：确保长推理期间 EventSource 连接不中断
                yield " "
                
                tool_calls_buffer = {}
                goto_tool_execution = False

                # 动态参数校准
                actual_model = request.model
                if agent_profile and agent_profile.model_config_id:
                    pm = await db.get(ProviderModel, agent_profile.model_config_id)
                    if pm: actual_model = pm.model_name
                
                # 工具列表准备
                tools_list = registry.get_all_actions()
                if agent_profile and agent_profile.tools:
                    if "*" not in agent_profile.tools:
                        tools_list = [t for t in tools_list if t.metadata.name in agent_profile.tools]
                
                openai_tools = [t.to_openai_format() for t in tools_list] if tools_list else []
                if enable_swarm and not any(t.get("function", {}).get("name") == "transfer_to_agent" for t in openai_tools):
                    openai_tools.append(swarm_service.get_handoff_tool_definition())

                # UI 净墨版动态路由 (仅首轮)
                if enable_swarm and openai_tools and current_iter == 1:
                    from sqlalchemy import select
                    from app.models.agent import AgentProfile
                    stmt = select(AgentProfile).where(AgentProfile.is_active == True)
                    experts_result = await db.execute(stmt)
                    all_experts = experts_result.scalars().all()
                    
                    found_target = None
                    query_low = current_query.lower()
                    for e in all_experts:
                        if e.name in query_low or (e.description and any(kw in query_low for kw in e.description.split())):
                            if e.id != agent_id:
                                found_target = e.id; break
                    
                    if found_target:
                        logger.info(f"[Swarm 6.4] 🧬 动态硬路由命中: {found_target}")
                        tool_calls_buffer[0] = {
                            "id": f"call_{uuid.uuid4().hex[:12]}",
                            "type": "function",
                            "function": {"name": "transfer_to_agent", "arguments": json.dumps({"agent_id": found_target})}
                        }
                        goto_tool_execution = True

                # 若未触发硬路由，则发起 AI 推理
                if not goto_tool_execution:
                    cleaned_internal = _clean_messages(internal_messages)
                    response_stream = await completion(
                        model=actual_model, messages=cleaned_internal,
                        tools=openai_tools if openai_tools else None,
                        tool_choice="auto" if openai_tools else None,
                        user_id=user_id, stream=True
                    )
                    
                    async for chunk in response_stream:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, "tool_calls") and delta.tool_calls:
                            for tc in delta.tool_calls:
                                idx = tc.index
                                if idx not in tool_calls_buffer:
                                    tool_calls_buffer[idx] = {"id": tc.id, "type": "function", "function": {"name": getattr(tc.function, "name", ""), "arguments": ""}}
                                if getattr(tc.function, "arguments", None): tool_calls_buffer[idx]["function"]["arguments"] += tc.function.arguments
                            continue
                            
                        if getattr(delta, "content", None):
                            total_assistant_content += delta.content
                            chunk_resp = ChatCompletionChunk(id=req_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=delta.content))])
                            yield f"data: {chunk_resp.model_dump_json(exclude_none=True)}\n\n"

                if tool_calls_buffer:
                    tool_calls_list = list(tool_calls_buffer.values())
                    internal_messages.append({"role": "assistant", "content": total_assistant_content or None, "tool_calls": tool_calls_list})
                    
                    tools_dict = {t.metadata.name: t for t in tools_list}
                    for tc in tool_calls_list:
                        func_name = tc["function"]["name"]
                        if func_name == "transfer_to_agent":
                            try:
                                args = json.loads(tc["function"]["arguments"])
                                tid = args.get("agent_id")
                                
                                if tid in called_expert_ids:
                                    logger.warning(f"[Swarm 6.4] 🛑 熔断触发: {tid}")
                                    m_text = "<collaboration>\n**系统提示**：专家 {} 已提供过建议，严禁重复分发。请你立即根据现有信息进行总结回复，不要再调用任何工具。\n</collaboration>".format(tid)
                                    internal_messages.append({"role": "tool", "name": "transfer_to_agent", "content": m_text, "tool_call_id": tc["id"]})
                                    continue
                                
                                called_expert_ids.add(tid)
                                expert = await swarm_service.handle_handoff(db, None, tid)
                                real_name = expert.name if expert else tid
                                
                                prog_text = "\n<collaboration>**核心调度通知**：正在为您协调专家 **{}** ...\n".format(real_name)
                                prog_chunk = ChatCompletionChunk(id=req_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=prog_text))])
                                yield "data: {}\n\n".format(prog_chunk.model_dump_json(exclude_none=True))
                                
                                full_text = ""
                                if expert:
                                    e_msgs = [{"role": "system", "content": expert.system_prompt or "你是一个专业的专家。"}, {"role": "user", "content": current_query}]
                                    expert_stream = await completion(model=actual_model, messages=e_msgs, user_id=user_id, stream=True)
                                    async for e_chunk in expert_stream:
                                        c = e_chunk.choices[0].delta.content or ""
                                        if c:
                                            full_text += c
                                            e_c = ChatCompletionChunk(id=req_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=c))])
                                            yield "data: {}\n\n".format(e_c.model_dump_json(exclude_none=True))
                                
                                end_chunk = ChatCompletionChunk(id=req_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content="\n</collaboration>\n"))])
                                yield "data: {}\n\n".format(end_chunk.model_dump_json(exclude_none=True))
                                
                                tool_res = "<collaboration>\n### 协作记录：专家 [{}] 的结论\n{}\n\n**[指令锁定]**：协同已完成，请直接基于上述内容回复用户，严禁再次调用专家。\n</collaboration>".format(real_name, full_text)
                                internal_messages.append({"role": "tool", "name": "transfer_to_agent", "content": tool_res, "tool_call_id": tc["id"]})
                            except Exception as e:
                                internal_messages.append({"role": "tool", "name": "transfer_to_agent", "content": f"Error: {e}", "tool_call_id": tc["id"]})
                    
                    # 回旋循环：主官在此基础上完成最终总结
                    continue
                else: 
                    break

            # 7. 终章持久化
            if session_id and db and total_assistant_content:
                db.add(ChatMessage(session_id=session_id, role="assistant", content=total_assistant_content, agent_id=agent_id))
                internal_messages.append({"role": "assistant", "content": total_assistant_content})
                await self._save_checkpoint(db, session_id, internal_messages, status="active", metadata={"agent_id": agent_id})
                if enable_memory:
                    asyncio.create_task(memory_service.extract_and_persist_facts(user_id, internal_messages.copy(), session_id))
            
            yield f"data: {ChatCompletionChunk(id=req_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(), finish_reason='stop')]).model_dump_json(exclude_none=True)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"[AgentService] Swarm 6.0 Stream error: {e}")
            raise e
        finally:
            if session_id and db:
                await self._save_checkpoint(db, session_id, internal_messages, status="active")
                await db.commit()

    async def chat(self, request: ChatCompletionRequest, db: AsyncSession, user_id: str, session_id: Optional[str] = None, enable_memory: bool = False, enable_swarm: bool = True) -> ChatCompletionResponse:
        full_content = ""
        req_id = f"chatcmpl-{uuid.uuid4().hex}"
        async for chunk in self.chat_stream(request=request, db=db, user_id=user_id, session_id=session_id, enable_memory=enable_memory, enable_swarm=enable_swarm, req_id=req_id):
            if isinstance(chunk, str) and chunk.startswith("data: "):
                try:
                    if "[DONE]" in chunk: continue
                    data = json.loads(chunk.replace("data: ", "").strip())
                    choice = data["choices"][0]
                    if "delta" in choice: full_content += choice["delta"].get("content") or ""
                    elif "message" in choice: full_content += choice["message"].get("content") or ""
                except Exception: continue
        return ChatCompletionResponse(id=req_id, model=request.model, choices=[ChatCompletionResponseChoice(index=0, message=ChatCompletionMessage(role="assistant", content=full_content))], usage=ChatCompletionUsage())

agent_service = AgentService()
