"""
图节点：专家路由（Handoff）

对应原 agent_service.py L421-444 的 transfer_to_agent 处理逻辑。
切换当前活跃的智能体 Profile，将控制权移交给指定专家。
"""
import json
import logging
from langgraph.types import RunnableConfig
from app.core.graph_state import AgentGraphState
from app.services.swarm_service import swarm_service

logger = logging.getLogger(__name__)


async def handoff_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """
    专家移交节点：切换当前活跃智能体为目标专家。

    从 pending_tool_calls 中提取 transfer_to_agent 调用，
    加载目标专家 Profile 并更新状态，同时追加 tool 结果消息。
    """
    c = config["configurable"]
    callback = c["stream_callback"]
    db = c["db"]
    session_id = c["session_id"]

    messages = list(state["messages"])
    pending_tool_calls = state["pending_tool_calls"]
    called_expert_ids = list(state["called_expert_ids"])
    iter_text = state["iter_text"]

    # 找出 transfer_to_agent / invoke_orchestrator 调用
    handoff_calls = [
        tc for tc in pending_tool_calls
        if tc.get("function", {}).get("name") in {"transfer_to_agent", "invoke_orchestrator"}
    ]

    # 先将 assistant 消息追加到历史（含所有 tool_calls，包括 handoff）
    messages.append({
        "role": "assistant",
        "content": iter_text or None,
        "tool_calls": list(pending_tool_calls)
    })

    new_agent_id = state["current_agent_id"]
    new_agent_profile = state["current_agent_profile"]

    for tc in handoff_calls:
        try:
            args = json.loads(tc["function"]["arguments"])
            tid = args.get("agent_id")
            tool_name = tc["function"]["name"]
            if not tid or tid in called_expert_ids:
                # 已调用过，追加失败消息
                messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": f"Skipped: agent '{tid}' already consulted.",
                    "tool_call_id": tc["id"]
                })
                continue

            target_agent = await swarm_service.handle_handoff(db, session_id, tid)
            if target_agent:
                called_expert_ids.append(tid)
                new_agent_id = target_agent.id
                new_agent_profile = {
                    "id": target_agent.id,
                    "name": target_agent.name,
                    "description": target_agent.description,
                    "system_prompt": target_agent.system_prompt,
                    "tools": target_agent.tools or [],
                    "model_config_id": target_agent.model_config_id,
                    "role": target_agent.role,
                    "routing_keywords": target_agent.routing_keywords,
                    "handoff_strategy": target_agent.handoff_strategy,
                    "is_public": target_agent.is_public,
                    "runtime_mode": "delegate_orchestrator" if tool_name == "invoke_orchestrator" else "expert",
                }
                await callback.emit(
                    f"data: {json.dumps({'type': 'status', 'state': 'active', 'agentName': target_agent.name, 'content': '正在分析任务细节...'})}\n\n"
                )
                messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": (
                        f"Successfully invoked sub-orchestrator: {target_agent.name}"
                        if tool_name == "invoke_orchestrator"
                        else f"Successfully consulted expert: {target_agent.name}"
                    ),
                    "tool_call_id": tc["id"]
                })
            else:
                messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": f"Agent Error: target agent '{tid}' unavailable for {tool_name}.",
                    "tool_call_id": tc["id"]
                })
        except Exception as ee:
            logger.error(f"[HandoffNode] Handoff failed: {ee}")
            messages.append({
                "role": "tool",
                "name": tc["function"]["name"],
                "content": f"Expert Error: {ee}",
                "tool_call_id": tc["id"]
            })

    return {
        "messages": messages,
        "current_agent_id": new_agent_id,
        "current_agent_profile": new_agent_profile,
        "called_expert_ids": called_expert_ids,
        "iter_text": "",
        "pending_tool_calls": [],
    }
