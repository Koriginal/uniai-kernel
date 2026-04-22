"""
图节点：专家汇总归还

对应原 agent_service.py L467-484 的专家完成后切回主控逻辑。
关闭 Collaboration 标签，将控制权归还给 Orchestrator，触发最终汇总。
"""
import json
import logging
from langgraph.types import RunnableConfig
from app.core.graph_state import AgentGraphState
from app.models.openai import (
    ChatCompletionChunk, ChatCompletionChunkChoice, ChatCompletionChunkDelta
)

logger = logging.getLogger(__name__)


async def synthesize_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """
    汇总归还节点：专家完成任务后，闭合 Collaboration 标签并切回 Orchestrator。

    状态变化：current_agent_id → orchestrator_agent_id
    """
    c = config["configurable"]
    callback = c["stream_callback"]
    model_name = c["model_name"]
    orchestrator_agent_id = c["orchestrator_agent_id"]
    orchestrator_profile = c["orchestrator_agent_profile"]
    request_id = c["request_id"]

    current_msg_id = state["current_msg_id"]
    stream_chunk_id = str(current_msg_id or request_id)
    wrapping_expert_id = state["wrapping_expert_id"]
    total_assistant_content = state["total_assistant_content"]
    current_agent_profile = state["current_agent_profile"]

    # 通知前端专家协作完成
    agent_name = current_agent_profile.get("name", "") if current_agent_profile else ""
    await callback.emit(
        f"data: {json.dumps({'type': 'status', 'state': 'completed', 'agentName': agent_name})}\n\n"
    )

    # 闭合 Collaboration 标签
    if wrapping_expert_id:
        closing_tag = "\n</collaboration>\n"
        close_chunk = ChatCompletionChunk(
            id=stream_chunk_id, model=model_name,
            choices=[ChatCompletionChunkChoice(index=0, delta=ChatCompletionChunkDelta(content=closing_tag))]
        ).model_dump_json(exclude_none=True)
        await callback.emit(f"data: {close_chunk}\n\n")
        total_assistant_content += closing_tag

    return {
        "current_agent_id": orchestrator_agent_id,
        "current_agent_profile": orchestrator_profile,
        "wrapping_expert_id": None,
        "total_assistant_content": total_assistant_content,
        "pending_tool_calls": [],
        "iter_text": "",
        "interaction_mode": "chat",
        "pending_delegate_type": None,
    }
