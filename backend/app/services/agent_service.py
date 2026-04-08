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
from app.services.audit_service import audit_service
from app.core.config import settings
from app.core.db import SessionLocal

logger = logging.getLogger(__name__)

class AgentService:
    """
    智能体核心业务引擎 - Swarm 多智能体协作制
    负责处理对话流、后台专家协助逻辑、上下文管理与视觉兼容。
    """

    async def _ensure_session_exists(self, db: AsyncSession, session_id: str, user_id: str, title: str = "New Chat", active_agent_id: str = None):
        if not session_id or not db:
            return
        result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
        session = result.scalar_one_or_none()
        if not session:
            logger.info(f"[AgentService] Auto-creating missing session: {session_id}")
            session = ChatSession(id=session_id, user_id=user_id, title=title, active_agent_id=active_agent_id)
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
        user_id: str,
        session_id: Optional[str] = None,
        enable_memory: bool = False,
        enable_swarm: bool = True,
        enable_canvas: bool = True,
        req_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        async with SessionLocal() as db:
            start_time = time.time()
            if not req_id:
                req_id = f"chatcmpl-{uuid.uuid4().hex}"

            # 初始清理
            original_msgs = [msg.model_dump(exclude_none=True) for msg in request.messages]
            internal_messages = _clean_messages(original_msgs)
            
            agent_profile = await swarm_service.get_active_agent_profile(db, session_id, request.model)
            agent_id = agent_profile.id if agent_profile else "agent-orchestrator"

            current_query = ""
            for msg in reversed(internal_messages):
                if msg.get("role") == "user":
                    content = msg.get("content")
                    if isinstance(content, list):
                        current_query = next((item.get("text", "") for item in content if item.get("type") == "text"), "")
                    else:
                        current_query = str(content)
                    break

            if session_id:
                can_resume = False
                session = await db.get(ChatSession, session_id)
                if session:
                    if session.active_agent_id != agent_id:
                        session.active_agent_id = agent_id
                        db.add(session)
                        await db.commit()
                    if session.thread_state and "messages" in session.thread_state:
                        if session.thread_state.get("agent_id") == agent_id:
                            can_resume = True

                if can_resume:
                    messages_raw = session.thread_state.get("messages", [])
                    internal_messages = _clean_messages(messages_raw)
                    internal_messages.append({"role": "user", "content": current_query})
                else:
                    await self._save_checkpoint(db, session_id, internal_messages, status="running", metadata={"agent_id": agent_id})
                    internal_messages = await context_service.build_context_messages(session_id=session_id, user_id=user_id, current_query=current_query, db_session=db, max_tokens=4096, enable_memory=enable_memory)
                
                if not getattr(request, 'skip_save_user', False):
                    user_msg = ChatMessage(session_id=session_id, role="user", content=current_query)
                    db.add(user_msg)
                    await db.commit()
                    yield f"data: {json.dumps({'type': 'metadata', 'user_message_id': user_msg.id})}\n\n"

            max_iterations = 10
            current_iter = 0
            called_expert_ids = set()
            total_assistant_content = ""
            total_prompt_tokens = 0
            total_completion_tokens = 0
            
            expert_prompt_catalog = ""
            if enable_swarm:
                expert_prompt_catalog = await swarm_service.get_expert_directory(db, user_id, agent_id)

            # 记录原始智能体（Orchestrator），用于后续智慧归还
            orchestrator_agent_id = agent_id
            orchestrator_profile = agent_profile

            current_msg_id = None
            if session_id:
                # 初始助手消息气泡
                initial_msg_db = ChatMessage(session_id=session_id, role="assistant", content="", agent_id=agent_id)
                db.add(initial_msg_db)
                await db.commit()
                current_msg_id = initial_msg_db.id
                yield f"data: {json.dumps({'type': 'metadata', 'assistant_message_id': current_msg_id, 'agentName': agent_profile.name if agent_profile else 'Assistant'})}\n\n"

            wrapping_expert_id = None
            total_tool_calls_list = []
            global_tool_index_offset = 0 # 全局工具索引偏移器，杜绝流式数据粘连
            try:
                while current_iter < max_iterations:
                    current_iter += 1
                    yield " " # Keep-alive heartbeat
                    
                    tool_calls_buffer = {}
                    echo_states = {} # 追踪每一路工具调用的回响状态（是否已发送 Markdown 栅栏）
                    # 动态注入当前活跃实体的系统提示词
                    current_sys_prompt = agent_profile.system_prompt if agent_profile and agent_profile.system_prompt else "你是一个有用的 AI 助手。"
                    
                    # --- 1. [SIDEBAR CANVAS MODE] ---
                    if enable_canvas:
                        # 开启状态：要求纯净源码，告知后端会自动包裹围栏同步到对话框
                        canvas_instr = "\n\n[SIDEBAR CANVAS: ENABLED]: \n" \
                                       "1. PURE SOURCE: In 'upsert_canvas' content field, provide RAW code ONLY. NO markdown fences (```). \n" \
                                       "2. AUTO-MIRROR: The system will automatically mirror your tool call to the chat with syntax highlighting. Do NOT repeat code in text. \n" \
                                       "3. SINGLE CALL: Only call 'upsert_canvas' once per turn with the final complete version."
                        current_sys_prompt += canvas_instr
                    else:
                        # 关闭状态：强力阻断指令，严禁调用工具，要求手动输出围栏
                        fallback_instr = "\n\n[SIDEBAR CANVAS: DISABLED]: \n" \
                                         "1. NO TOOL: The 'upsert_canvas' tool is REMOVED. NEVER attempt to call it. \n" \
                                         "2. MANUAL FENCES: You MUST output all code segments directly in your chat response using standard Markdown triple backticks (```). \n" \
                                         "3. NO MENTION: Do NOT mention the 'sidebar' or 'canvas' to the user."
                        current_sys_prompt += fallback_instr

                    # --- 2. [COLLABORATION & SWARM PROTOCOL] ---
                    if enable_swarm and agent_id != orchestrator_agent_id:
                        protocol_instr = f"\n\n[COLLABORATION PROTOCOL]: \n" \
                                         f"1. MANDATORY: Output your logic/reasoning first. \n" \
                                         f"2. ZERO-SILENCE: Always explain what you are providing. \n" \
                                         f"3. HANDBACK: Call 'transfer_to_agent' with id='{orchestrator_agent_id}' to finish."
                        current_sys_prompt += protocol_instr
                    
                    # --- 3. [ORCHESTRATOR STEWARDSHIP] ---
                    if agent_id == orchestrator_agent_id:
                        steward_instr = "\n\n[ORCHESTRATOR DUTY]: \n" \
                                        "1. NO REPETITION: Do NOT repeat code blocks from experts. \n" \
                                        "2. BRIEF: Keep final response to 1-2 professional sentences. \n" \
                                        "3. FALLBACK: Direct 'upsert_canvas' (RAW ONLY) only if expert failed."
                        current_sys_prompt += steward_instr

                    full_sys_content = (expert_prompt_catalog + "\n\n" + current_sys_prompt).strip()

                    # 确保系统消息处于首位且实时更新
                    sys_found = False
                    for m in internal_messages:
                        if m.get("role") == "system":
                            m["content"] = full_sys_content
                            sys_found = True
                            break
                    if not sys_found:
                        internal_messages.insert(0, {"role": "system", "content": full_sys_content})

                    actual_model = request.model
                    if agent_profile and agent_profile.model_config_id:
                        pm = await db.get(ProviderModel, agent_profile.model_config_id)
                        if pm: actual_model = pm.model_name
                    
                    tools_list = registry.get_all_actions()
                    if agent_profile and agent_profile.tools:
                        if "*" not in agent_profile.tools:
                            tools_list = [t for t in tools_list if t.metadata.name in agent_profile.tools]
                        
                    openai_tools = [t.to_openai_format() for t in tools_list] if tools_list else []
                    
                    if enable_canvas:
                        canvas_tool = registry.get_action("upsert_canvas")
                        if canvas_tool and not any(t.get("function", {}).get("name") == "upsert_canvas" for t in openai_tools):
                            openai_tools.append(canvas_tool.to_openai_format())
                            
                    if enable_swarm and not any(t.get("function", {}).get("name") == "transfer_to_agent" for t in openai_tools):
                        openai_tools.append(swarm_service.get_handoff_tool_definition())

                    # --- 执行当前角色（主控或专家）呼叫 ---
                    cleaned_internal = _clean_messages(internal_messages)
                    
                    # 终极协议屏蔽：绝不允许大模型在上下文里看到这套临时协议标签，防止幻觉复现
                    import re
                    for m in cleaned_internal:
                        if m.get("role") == "assistant" and isinstance(m.get("content"), str):
                            m["content"] = re.sub(r"<\/?collaboration[^>]*>", "", m["content"]).strip()
                            
                    try:
                        response_stream = await completion(
                            model=actual_model, 
                            messages=cleaned_internal, 
                            tools=openai_tools if openai_tools else None, 
                            tool_choice="auto" if openai_tools else None, 
                            user_id=user_id, 
                            stream=True, 
                            stream_options={"include_usage": True}
                        )
                        
                        # 不管新角色是谁，只要发生了实体更换，必须先严谨地闭合上一位专家的标签！
                        is_expert = agent_id != orchestrator_agent_id
                        
                        if wrapping_expert_id and wrapping_expert_id != agent_id:
                            closing_tag = "\n</collaboration>\n"
                            yield f"data: {ChatCompletionChunk(id=current_msg_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=closing_tag))]).model_dump_json(exclude_none=True)}\n\n"
                            total_assistant_content += closing_tag
                            wrapping_expert_id = None

                        iter_text = ""
                        # 注意：如果我们即将开始镜像，我们将延迟开启标签
                        # 但这里是迭代起始，我们先检测是否是专家
                        if is_expert and not wrapping_expert_id:
                            opening_tag = f"\n<collaboration title='{agent_profile.name if agent_profile else 'Expert'}'>\n"
                            yield f"data: {ChatCompletionChunk(id=current_msg_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=opening_tag))]).model_dump_json(exclude_none=True)}\n\n"
                            total_assistant_content += opening_tag
                            wrapping_expert_id = agent_id
                        
                        # 向前端透传更细粒度的原子状态
                        state_msg = "正在深入分析中..." if is_expert else "正在进行最后汇总..."
                        yield f"data: {json.dumps({'type': 'status', 'state': 'active', 'agentName': agent_profile.name if agent_profile else 'Assistant', 'content': state_msg})}\n\n"

                        # 核心：分轮次偏移工具索引，杜绝前端数据粘连与 JSON 损坏
                        max_idx_in_iter = 0 # 本轮迭代中产生的最大索引
                        
                        async for chunk in response_stream:
                            if not chunk or not chunk.choices: continue
                            delta = chunk.choices[0].delta if chunk.choices else None
                            
                            # 处理工具调用偏移逻辑
                            if delta and hasattr(delta, "tool_calls") and delta.tool_calls:
                                # 为每一帧工具调用应用全局偏移，使专家与主控的索引物理隔离
                                for tc in delta.tool_calls:
                                    tc.index += global_tool_index_offset
                                    if (tc.index - global_tool_index_offset + 1) > max_idx_in_iter:
                                        max_idx_in_iter = (tc.index - global_tool_index_offset + 1)
                                
                                chunk.id = current_msg_id
                                yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"
                                
                                for tc in delta.tool_calls:
                                    idx = tc.index
                                    if idx not in tool_calls_buffer:
                                        tool_calls_buffer[idx] = {"id": tc.id, "type": "function", "function": {"name": "", "arguments": ""}}
                                    
                                    # [FIX] 保护名称：只有当 tc.function.name 非空时才创建或更新名称，防止被后续 chunk 覆盖为空
                                    if getattr(tc.function, "name", None):
                                        tool_calls_buffer[idx]["function"]["name"] = tc.function.name
                                        
                                    if getattr(tc.function, "arguments", None): 
                                        tool_calls_buffer[idx]["function"]["arguments"] += tc.function.arguments
                                        
                                        # 【万能镜像回响】：无论 enable_canvas 是否开启，只要模型由于幻觉或需要产生工具调用，均进行回响备份
                                        if tool_calls_buffer[idx]["function"]["name"] == "upsert_canvas":
                                            # 【破圈逻辑】：镜像开始前，如果处于协作折叠框内，立即将其闭合，使代码直接泄露到主聊天流中
                                            if wrapping_expert_id:
                                                closing_tag = "\n</collaboration>\n"
                                                yield f"data: {ChatCompletionChunk(id=current_msg_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=closing_tag))]).model_dump_json(exclude_none=True)}\n\n"
                                                total_assistant_content += closing_tag
                                                wrapping_expert_id = None

                                            if idx not in echo_states:
                                                echo_states[idx] = {"opened": False, "closed": False, "language": "markdown", "yielded_len": 0}
                                            
                                            args_so_far = tool_calls_buffer[idx]["function"]["arguments"]
                                            
                                            # [Smart Detection] 持续探测语言信息，直到围栏开启为止
                                            if not echo_states[idx]["opened"] or echo_states[idx]["language"] == "markdown":
                                                lang_match = re.search(r'"language"\s*:\s*"([^"]*)"', args_so_far)
                                                if lang_match:
                                                    echo_states[idx]["language"] = lang_match.group(1) or "markdown"

                                            # 【精准提取】寻找 content 字段的内容起始位置
                                            content_match = re.search(r'"content"\s*:\s*"', args_so_far)
                                            if content_match:
                                                # 如果还没有发送开场围栏，现在发送
                                                if not echo_states[idx]["opened"]:
                                                    # 发送围栏时，采用目前能探测到的最精准语言（默认为 markdown）
                                                    lang = echo_states[idx]["language"]
                                                    open_fence = f"\n\n```{lang}\n"
                                                    echo_chunk = ChatCompletionChunk(id=current_msg_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=open_fence))])
                                                    yield f"data: {echo_chunk.model_dump_json(exclude_none=True)}\n\n"
                                                    total_assistant_content += open_fence
                                                    echo_states[idx]["opened"] = True
                                                
                                                # 提取当前已生成的全部 content 内容
                                                # 我们寻找 content 字段的起始引号之后，到当前末尾（或结束引号之前）的部分
                                                content_start_pos = content_match.end()
                                                # 查找下一个未转义的引号作为结束
                                                # 注意：因为是流式，可能还没结束
                                                content_val_raw = args_so_far[content_start_pos:]
                                                
                                                # 尝试截断掉可能的结束引号及其之后的内容
                                                actual_end = -1
                                                for i in range(len(content_val_raw)):
                                                    if content_val_raw[i] == '"' and (i == 0 or content_val_raw[i-1] != '\\'):
                                                        actual_end = i
                                                        break
                                                
                                                is_fully_closed = (actual_end != -1)
                                                current_full_val = content_val_raw[:actual_end] if is_fully_closed else content_val_raw
                                                
                                                # 处理转义字符还原
                                                decoded_val = current_full_val.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\').replace('\\t', '\t')
                                                
                                                # 【增量发送】
                                                new_text = decoded_val[echo_states[idx]["yielded_len"]:]
                                                if new_text:
                                                    echo_chunk = ChatCompletionChunk(id=current_msg_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=new_text))])
                                                    yield f"data: {echo_chunk.model_dump_json(exclude_none=True)}\n\n"
                                                    total_assistant_content += new_text
                                                    echo_states[idx]["yielded_len"] += len(new_text)
                                                
                                                # 如果内容已闭合且尚未发送结束围栏
                                                if is_fully_closed and not echo_states[idx]["closed"]:
                                                    close_fence = "\n```\n"
                                                    echo_chunk = ChatCompletionChunk(id=current_msg_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=close_fence))])
                                                    yield f"data: {echo_chunk.model_dump_json(exclude_none=True)}\n\n"
                                                    total_assistant_content += close_fence
                                                    echo_states[idx]["closed"] = True
                            
                            if delta and getattr(delta, "content", None):
                                c = delta.content
                                
                                # [Smart Resume] 如果镜像回响导致了标签提前闭合，而现在又有新的文字内容，重新开启专家折叠框
                                if is_expert and not wrapping_expert_id:
                                    opening_tag = f"\n<collaboration title='{agent_profile.name if agent_profile else 'Expert'}'>\n"
                                    yield f"data: {ChatCompletionChunk(id=current_msg_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=opening_tag))]).model_dump_json(exclude_none=True)}\n\n"
                                    total_assistant_content += opening_tag
                                    wrapping_expert_id = agent_id

                                iter_text += c
                                total_assistant_content += c
                                chunk_resp = ChatCompletionChunk(id=current_msg_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=c))])
                                yield f"data: {chunk_resp.model_dump_json(exclude_none=True)}\n\n"
                            
                            if getattr(chunk, "usage", None):
                                total_prompt_tokens += chunk.usage.prompt_tokens
                                total_completion_tokens += chunk.usage.completion_tokens
                        
                        # 本轮迭代结束，更新全局偏移量，确保下一轮模型输出的 index 项不会与本轮冲突
                        global_tool_index_offset += max_idx_in_iter

                        # 关键细节：累加所有迭代的工具调用记录
                        if tool_calls_buffer:
                            total_tool_calls_list.extend(list(tool_calls_buffer.values()))

                        # 关键细节：必须存储全量累积文本 total_assistant_content，而非仅本轮 iter_text。
                        # 否则每一轮迭代（如专家接力）都会在数据库中覆盖掉上一轮的内容，导致刷新后只能看到最后一步。
                        if session_id and current_msg_id:
                            msg_to_update = await db.get(ChatMessage, current_msg_id)
                            if msg_to_update:
                                if total_assistant_content: msg_to_update.content = total_assistant_content
                                if total_tool_calls_list:
                                    msg_to_update.tool_calls = list(total_tool_calls_list)  # Force JSON mutation detection
                                db.add(msg_to_update)
                                await db.commit()

                    except Exception as e:
                        logger.error(f"[AgentService] Iteration failed: {e}")
                        err_chunk = ChatCompletionChunk(id=current_msg_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=f"\n❌ 内核严重故障: {str(e)}"))])
                        yield f"data: {err_chunk.model_dump_json(exclude_none=True)}\n\n"
                        break

                    # --- 工具执行与气泡接力处理 ---
                    if tool_calls_buffer:
                        tool_calls_list = list(tool_calls_buffer.values())
                        internal_messages.append({"role": "assistant", "content": iter_text or None, "tool_calls": tool_calls_list})
                        
                        found_handoff = False
                        for tc in tool_calls_list:
                            func_name = tc["function"]["name"]
                            if func_name == "transfer_to_agent":
                                try:
                                    args = json.loads(tc["function"]["arguments"])
                                    tid = args.get("agent_id")
                                    if tid in called_expert_ids: continue
                                    called_expert_ids.add(tid)
                                    expert = await swarm_service.handle_handoff(db, session_id, tid)
                                    
                                    if expert:
                                        # 核心逻辑：发起接力，但共用同一个消息 ID
                                        found_handoff = True
                                        agent_profile = expert
                                        agent_id = expert.id
                                        
                                        # 仅通知前端协作状态变更，不切换物理会话的主人（active_agent_id）。
                                        # 顶部标题栏应始终保持初始专家/主控的身份。
                                        yield f"data: {json.dumps({'type': 'status', 'state': 'active', 'agentName': agent_profile.name, 'content': '正在分析任务细节...'})}\n\n"
                                        
                                        internal_messages.append({"role": "tool", "name": "transfer_to_agent", "content": f"Successfully consulted expert: {agent_profile.name}", "tool_call_id": tc["id"]})
                                except Exception as ee:
                                    logger.error(f"[AgentService] Expert handoff logic failure: {ee}")
                                    internal_messages.append({"role": "tool", "name": "transfer_to_agent", "content": f"Expert Error: {ee}", "tool_call_id": tc["id"]})
                            else:
                                # 普通工具（搜索、看板、计算等）原生执行
                                try:
                                    action = registry.get_action(func_name)
                                    if action:
                                        # 对于普通工具调用，通知用户具体是在做什么
                                        yield f"data: {json.dumps({'type': 'status', 'state': 'active', 'agentName': agent_profile.name, 'content': f'正在执行 {func_name}...'})}\n\n"
                                        
                                        args = json.loads(tc["function"]["arguments"])
                                        res = await action.execute(**args)
                                        internal_messages.append({"role": "tool", "name": func_name, "content": str(res), "tool_call_id": tc["id"]})
                                except Exception as te:
                                    internal_messages.append({"role": "tool", "name": func_name, "content": f"Tool Error: {te}", "tool_call_id": tc["id"]})
                        
                        # 如果发生了角色移交，立即重启主循环进入新角色思维
                        if found_handoff:
                            continue
                        
                        # 普通工具执行后，继续当前角色的思考
                        continue
                    else:
                        # 既没有后续工具，也没有内容生成（或已完成最终输出）
                        # 智慧自动归还：当专家任务完成且不再需要工具时，自动切回主助收尾
                        if agent_id != orchestrator_agent_id:
                            # 标记专家协作状态已完成
                            yield f"data: {json.dumps({'type': 'status', 'state': 'completed', 'agentName': agent_profile.name})}\n\n"
                            
                            # 重置身份为主助手
                            agent_id = orchestrator_agent_id
                            agent_profile = orchestrator_profile
                            
                            if wrapping_expert_id:
                                closing_tag = "\n</collaboration>\n"
                                yield f"data: {json.dumps({'choices': [{'index': 0, 'delta': {'content': closing_tag}}]})}\n\n"
                                total_assistant_content += closing_tag
                                wrapping_expert_id = None
                                
                            # 移除非必要的最终总结消息拆分，共用 ID
                            continue # 重启主循环开启总结
                        
                        # 主助手也已完成所有工作，正式退出
                        break

                # --- 全局收尾与持久化 ---
                if wrapping_expert_id:
                    closing_tag = "\n</collaboration>\n"
                    yield f"data: {json.dumps({'choices': [{'index': 0, 'delta': {'content': closing_tag}}]})}\n\n"
                    total_assistant_content += closing_tag
                    wrapping_expert_id = None

                if session_id and total_assistant_content:
                    internal_messages = _clean_messages(internal_messages)
                    if not any(m.get("role") == "assistant" and m.get("content") == total_assistant_content for m in internal_messages):
                        internal_messages.append({"role": "assistant", "content": total_assistant_content})
                    await self._save_checkpoint(db, session_id, internal_messages, status="active", metadata={"agent_id": orchestrator_agent_id})
                
                yield f"data: {ChatCompletionChunk(id=req_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(), finish_reason='stop')]).model_dump_json(exclude_none=True)}\n\n"
                yield "data: [DONE]\n\n"

            except Exception as outer_e:
                logger.error(f"[AgentService] Core stream crash: {outer_e}")
                err_c = ChatCompletionChunk(id=req_id, model=request.model, choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=f"\n❌ 内核严重故障: {str(outer_e)}"))])
                yield f"data: {err_c.model_dump_json(exclude_none=True)}\n\n"
            finally:
                if session_id:
                    await db.commit()

    async def chat(self, request: ChatCompletionRequest, user_id: str, session_id: Optional[str] = None, enable_memory: bool = False, enable_swarm: bool = True, enable_canvas: bool = True) -> ChatCompletionResponse:
        full_content = ""
        req_id = f"chatcmpl-{uuid.uuid4().hex}"
        async for chunk in self.chat_stream(request=request, user_id=user_id, session_id=session_id, enable_memory=enable_memory, enable_swarm=enable_swarm, enable_canvas=enable_canvas, req_id=req_id):
            if isinstance(chunk, str) and chunk.startswith("data: "):
                try:
                    if "[DONE]" in chunk: continue
                    data = json.loads(chunk.replace("data: ", "").strip())
                    if data.get("type") == "metadata": continue
                    choice = data["choices"][0]
                    if "delta" in choice: full_content += choice["delta"].get("content") or ""
                except Exception: continue
        return ChatCompletionResponse(id=req_id, model=request.model, choices=[ChatCompletionResponseChoice(index=0, message=ChatCompletionMessage(role="assistant", content=full_content))], usage=ChatCompletionUsage())

agent_service = AgentService()
