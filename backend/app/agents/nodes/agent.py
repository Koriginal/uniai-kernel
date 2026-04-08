"""
图节点：LLM 思考 + 流式输出

对应原 agent_service.py L165-391 的核心流式循环体。
调用 LLM，处理流式 token，管理 Canvas 镜像回响和 Collaboration 标签。
"""
import re
import json
import logging
from langgraph.types import RunnableConfig
from app.core.graph_state import AgentGraphState
from app.core.llm import completion, _clean_messages
from app.core.plugins import registry
from app.models.openai import (
    ChatCompletionChunk, ChatCompletionChunkChoice, ChatCompletionChunkDelta
)
from app.models.provider import ProviderModel
from app.models.message import ChatMessage

logger = logging.getLogger(__name__)


async def agent_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """
    核心推理节点：调用 LLM，流式输出 token，解析 tool_calls。

    该节点对应原 while 循环内每一轮的流式调用部分，包括：
    - 动态注入 System Prompt（Canvas/Swarm/Protocol 指令）
    - 流式解析 tool_calls 和文本 delta
    - Canvas 镜像回响（围栏包裹）
    - Collaboration 标签管理（专家包装）
    - 更新数据库中的助手消息
    """
    c = config["configurable"]
    callback = c["stream_callback"]
    db = c["db"]
    session_id = c["session_id"]
    request_id = c["request_id"]
    model_name = c["model_name"]
    enable_canvas = c.get("enable_canvas", True)
    enable_swarm = c.get("enable_swarm", True)
    orchestrator_agent_id = c["orchestrator_agent_id"]
    expert_prompt_catalog = c.get("expert_prompt_catalog", "")

    messages = list(state["messages"])
    current_agent_id = state["current_agent_id"]
    agent_profile = state["current_agent_profile"]
    current_msg_id = state["current_msg_id"]
    total_assistant_content = state["total_assistant_content"]
    total_tool_calls_list = list(state["total_tool_calls_list"])
    global_tool_index_offset = state["global_tool_index_offset"]
    wrapping_expert_id = state["wrapping_expert_id"]
    iteration_count = state["iteration_count"] + 1

    is_expert = current_agent_id != orchestrator_agent_id

    # ---- 1. 构建本轮 System Prompt ----
    current_sys_prompt = (agent_profile.get("system_prompt") if agent_profile else None) or "你是一个有用的 AI 助手。"

    if enable_canvas:
        canvas_instr = (
            "\n\n[SIDEBAR CANVAS: ENABLED]: \n"
            "1. PURE SOURCE: In 'upsert_canvas' content field, provide RAW code ONLY. NO markdown fences (```). \n"
            "2. AUTO-MIRROR: The system will automatically mirror your tool call to the chat with syntax highlighting. Do NOT repeat code in text. \n"
            "3. SINGLE CALL: Only call 'upsert_canvas' once per turn with the final complete version."
        )
        current_sys_prompt += canvas_instr
    else:
        fallback_instr = (
            "\n\n[SIDEBAR CANVAS: DISABLED]: \n"
            "1. NO TOOL: The 'upsert_canvas' tool is REMOVED. NEVER attempt to call it. \n"
            "2. MANUAL FENCES: You MUST output all code segments directly in your chat response using standard Markdown triple backticks (```). \n"
            "3. NO MENTION: Do NOT mention the 'sidebar' or 'canvas' to the user."
        )
        current_sys_prompt += fallback_instr

    if enable_swarm and is_expert:
        protocol_instr = (
            f"\n\n[COLLABORATION PROTOCOL]: \n"
            f"1. MANDATORY: Output your logic/reasoning first. \n"
            f"2. ZERO-SILENCE: Always explain what you are providing. \n"
            f"3. HANDBACK: Call 'transfer_to_agent' with id='{orchestrator_agent_id}' to finish."
        )
        current_sys_prompt += protocol_instr

    if current_agent_id == orchestrator_agent_id:
        steward_instr = (
            "\n\n[ORCHESTRATOR DUTY]: \n"
            "1. NO REPETITION: Do NOT repeat code blocks from experts. \n"
            "2. BRIEF: Keep final response to 1-2 professional sentences. \n"
            "3. FALLBACK: Direct 'upsert_canvas' (RAW ONLY) only if expert failed."
        )
        current_sys_prompt += steward_instr

    full_sys_content = (expert_prompt_catalog + "\n\n" + current_sys_prompt).strip()

    # 确保 system 消息处于首位且更新
    sys_found = False
    for m in messages:
        if m.get("role") == "system":
            m["content"] = full_sys_content
            sys_found = True
            break
    if not sys_found:
        messages.insert(0, {"role": "system", "content": full_sys_content})

    # ---- 2. 确定模型和工具列表 ----
    actual_model = model_name
    if agent_profile and agent_profile.get("model_config_id"):
        pm = await db.get(ProviderModel, agent_profile["model_config_id"])
        if pm:
            actual_model = pm.model_name

    tools_list = registry.get_all_actions()
    if agent_profile and agent_profile.get("tools"):
        if "*" not in agent_profile["tools"]:
            tools_list = [t for t in tools_list if t.metadata.name in agent_profile["tools"]]

    openai_tools = [t.to_openai_format() for t in tools_list] if tools_list else []

    if enable_canvas:
        canvas_tool = registry.get_action("upsert_canvas")
        if canvas_tool and not any(t.get("function", {}).get("name") == "upsert_canvas" for t in openai_tools):
            openai_tools.append(canvas_tool.to_openai_format())

    if enable_swarm and not any(t.get("function", {}).get("name") == "transfer_to_agent" for t in openai_tools):
        from app.services.swarm_service import swarm_service
        openai_tools.append(swarm_service.get_handoff_tool_definition())

    # ---- 3. 协作标签开场 ----
    if is_expert and not wrapping_expert_id:
        opening_tag = f"\n<collaboration title='{agent_profile.get('name', 'Expert') if agent_profile else 'Expert'}'>\n"
        chunk_data = ChatCompletionChunk(
            id=current_msg_id, model=model_name,
            choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=opening_tag))]
        ).model_dump_json(exclude_none=True)
        await callback.emit(f"data: {chunk_data}\n\n")
        total_assistant_content += opening_tag
        wrapping_expert_id = current_agent_id

    state_msg = "正在深入分析中..." if is_expert else "正在进行最后汇总..."
    await callback.emit(f"data: {json.dumps({'type': 'status', 'state': 'active', 'agentName': agent_profile.get('name', 'Assistant') if agent_profile else 'Assistant', 'content': state_msg})}\n\n")

    # ---- 4. 流式调用 LLM ----
    cleaned_internal = _clean_messages(messages)
    for m in cleaned_internal:
        if m.get("role") == "assistant" and isinstance(m.get("content"), str):
            m["content"] = re.sub(r"<\/?collaboration[^>]*>", "", m["content"]).strip()

    tool_calls_buffer = {}
    echo_states = {}
    iter_text = ""
    max_idx_in_iter = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    try:
        response_stream = await completion(
            model=actual_model,
            messages=cleaned_internal,
            tools=openai_tools if openai_tools else None,
            tool_choice="auto" if openai_tools else None,
            user_id=c.get("user_id", "admin"),
            stream=True,
            stream_options={"include_usage": True}
        )

        async for chunk in response_stream:
            if not chunk or not chunk.choices:
                continue
            delta = chunk.choices[0].delta if chunk.choices else None

            # 处理 tool_calls 流
            if delta and hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc in delta.tool_calls:
                    tc.index += global_tool_index_offset
                    if (tc.index - global_tool_index_offset + 1) > max_idx_in_iter:
                        max_idx_in_iter = (tc.index - global_tool_index_offset + 1)

                chunk.id = current_msg_id
                await callback.emit(f"data: {chunk.model_dump_json(exclude_none=True)}\n\n")

                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {"id": tc.id, "type": "function", "function": {"name": "", "arguments": ""}}

                    if getattr(tc.function, "name", None):
                        tool_calls_buffer[idx]["function"]["name"] = tc.function.name

                    if getattr(tc.function, "arguments", None):
                        tool_calls_buffer[idx]["function"]["arguments"] += tc.function.arguments

                        # Canvas 镜像回响
                        if tool_calls_buffer[idx]["function"]["name"] == "upsert_canvas":
                            # 如果在 collaboration 框内，先闭合
                            if wrapping_expert_id:
                                closing_tag = "\n</collaboration>\n"
                                close_chunk = ChatCompletionChunk(
                                    id=current_msg_id, model=model_name,
                                    choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=closing_tag))]
                                ).model_dump_json(exclude_none=True)
                                await callback.emit(f"data: {close_chunk}\n\n")
                                total_assistant_content += closing_tag
                                wrapping_expert_id = None

                            if idx not in echo_states:
                                echo_states[idx] = {"opened": False, "closed": False, "language": "markdown", "yielded_len": 0}

                            args_so_far = tool_calls_buffer[idx]["function"]["arguments"]

                            if not echo_states[idx]["opened"] or echo_states[idx]["language"] == "markdown":
                                lang_match = re.search(r'"language"\s*:\s*"([^"]*)"', args_so_far)
                                if lang_match:
                                    echo_states[idx]["language"] = lang_match.group(1) or "markdown"

                            content_match = re.search(r'"content"\s*:\s*"', args_so_far)
                            if content_match:
                                if not echo_states[idx]["opened"]:
                                    lang = echo_states[idx]["language"]
                                    open_fence = f"\n\n```{lang}\n"
                                    fence_chunk = ChatCompletionChunk(
                                        id=current_msg_id, model=model_name,
                                        choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=open_fence))]
                                    ).model_dump_json(exclude_none=True)
                                    await callback.emit(f"data: {fence_chunk}\n\n")
                                    total_assistant_content += open_fence
                                    echo_states[idx]["opened"] = True

                                content_start_pos = content_match.end()
                                content_val_raw = args_so_far[content_start_pos:]

                                actual_end = -1
                                for i in range(len(content_val_raw)):
                                    if content_val_raw[i] == '"' and (i == 0 or content_val_raw[i-1] != '\\'):
                                        actual_end = i
                                        break

                                is_fully_closed = (actual_end != -1)
                                current_full_val = content_val_raw[:actual_end] if is_fully_closed else content_val_raw
                                decoded_val = (current_full_val
                                               .replace('\\n', '\n').replace('\\"', '"')
                                               .replace('\\r', '')
                                               .replace('\\\\', '\\').replace('\\t', '\t'))

                                new_text = decoded_val[echo_states[idx]["yielded_len"]:]
                                if new_text:
                                    echo_chunk = ChatCompletionChunk(
                                        id=current_msg_id, model=model_name,
                                        choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=new_text))]
                                    ).model_dump_json(exclude_none=True)
                                    await callback.emit(f"data: {echo_chunk}\n\n")
                                    total_assistant_content += new_text
                                    echo_states[idx]["yielded_len"] += len(new_text)

                                if is_fully_closed and not echo_states[idx]["closed"]:
                                    close_fence = "\n```\n"
                                    fence_chunk = ChatCompletionChunk(
                                        id=current_msg_id, model=model_name,
                                        choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=close_fence))]
                                    ).model_dump_json(exclude_none=True)
                                    await callback.emit(f"data: {fence_chunk}\n\n")
                                    total_assistant_content += close_fence
                                    echo_states[idx]["closed"] = True

            # 处理文本 delta
            if delta and getattr(delta, "content", None):
                c_text = delta.content
                if is_expert and not wrapping_expert_id:
                    opening_tag = f"\n<collaboration title='{agent_profile.get('name', 'Expert') if agent_profile else 'Expert'}'>\n"
                    tag_chunk = ChatCompletionChunk(
                        id=current_msg_id, model=model_name,
                        choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=opening_tag))]
                    ).model_dump_json(exclude_none=True)
                    await callback.emit(f"data: {tag_chunk}\n\n")
                    total_assistant_content += opening_tag
                    wrapping_expert_id = current_agent_id

                iter_text += c_text
                total_assistant_content += c_text
                text_chunk = ChatCompletionChunk(
                    id=current_msg_id, model=model_name,
                    choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=c_text))]
                ).model_dump_json(exclude_none=True)
                await callback.emit(f"data: {text_chunk}\n\n")

            if getattr(chunk, "usage", None):
                total_prompt_tokens += chunk.usage.prompt_tokens
                total_completion_tokens += chunk.usage.completion_tokens

    except Exception as e:
        logger.error(f"[AgentNode] LLM call failed: {e}")
        err_chunk = ChatCompletionChunk(
            id=current_msg_id, model=model_name,
            choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=f"\n❌ 内核故障: {str(e)}"))]
        ).model_dump_json(exclude_none=True)
        await callback.emit(f"data: {err_chunk}\n\n")

    # ---- 5. 更新全局偏移量 ----
    new_global_offset = global_tool_index_offset + max_idx_in_iter

    # ---- 6. 累计 tool_calls ----
    pending_tool_calls = []
    if tool_calls_buffer:
        pending_tool_calls = list(tool_calls_buffer.values())
        total_tool_calls_list.extend(pending_tool_calls)

    # ---- 7. 持久化当前消息 ----
    if session_id and current_msg_id:
        try:
            msg_to_update = await db.get(ChatMessage, current_msg_id)
            if msg_to_update:
                if total_assistant_content:
                    msg_to_update.content = total_assistant_content
                if total_tool_calls_list:
                    msg_to_update.tool_calls = list(total_tool_calls_list)
                db.add(msg_to_update)
                await db.commit()
        except Exception as e:
            logger.error(f"[AgentNode] Message persist failed: {e}")

    return {
        "messages": messages,
        "pending_tool_calls": pending_tool_calls,
        "has_pending_handoff": False,
        "handoff_target_id": None,
        "wrapping_expert_id": wrapping_expert_id,
        "total_assistant_content": total_assistant_content,
        "total_tool_calls_list": total_tool_calls_list,
        "global_tool_index_offset": new_global_offset,
        "iter_text": iter_text,
        "iteration_count": iteration_count,
    }
