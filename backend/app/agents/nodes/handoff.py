"""
图节点：专家路由（Handoff）

只处理 transfer_to_agent 调用，将控制权移交给指定专家。
子主控调用由 orchestrator_invoke_node 单独处理。
"""
import json
import logging
from langgraph.types import RunnableConfig
from app.agents.task_runtime import (
    advance_execution_plan,
    build_task_runtime_update_event,
    persist_task_runtime_state,
    record_execution_artifact,
)
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
    task_frame = state.get("task_frame") or {}
    execution_plan = state.get("execution_plan") or {}
    execution_artifacts = list(state.get("execution_artifacts") or [])

    # 找出 transfer_to_agent 调用
    handoff_calls = [
        tc for tc in pending_tool_calls
        if tc.get("function", {}).get("name") == "transfer_to_agent"
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
            execution_plan = advance_execution_plan(
                execution_plan,
                event_type="handoff_start",
                payload={"agent_id": tid, "tool_call_id": tc.get("id")},
            )
            if not tid or tid in called_expert_ids:
                # 已调用过，追加失败消息
                messages.append({
                    "role": "tool",
                    "name": "transfer_to_agent",
                    "content": f"Skipped: agent '{tid}' already consulted.",
                    "tool_call_id": tc["id"]
                })
                execution_plan = advance_execution_plan(
                    execution_plan,
                    event_type="handoff_skipped",
                    payload={"agent_id": tid, "status": "blocked", "tool_call_id": tc.get("id")},
                )
                continue

            expert = await swarm_service.handle_handoff(db, session_id, tid)
            if expert and expert.role == "expert":
                called_expert_ids.append(tid)
                new_agent_id = expert.id
                new_agent_profile = {
                    "id": expert.id,
                    "name": expert.name,
                    "description": expert.description,
                    "system_prompt": expert.system_prompt,
                    "tools": expert.tools or [],
                    "model_config_id": expert.model_config_id,
                    "role": expert.role,
                    "routing_keywords": expert.routing_keywords,
                    "handoff_strategy": expert.handoff_strategy,
                    "is_public": expert.is_public,
                    "runtime_mode": "expert",
                }
                await callback.emit(
                    f"data: {json.dumps({'type': 'status', 'state': 'active', 'agentName': expert.name, 'content': '正在分析任务细节...'})}\n\n"
                )
                messages.append({
                    "role": "tool",
                    "name": "transfer_to_agent",
                    "content": f"Successfully consulted expert: {expert.name}",
                    "tool_call_id": tc["id"]
                })
                payload = {
                    "agent_id": expert.id,
                    "status": "success",
                    "tool_call_id": tc.get("id"),
                    "result": {"preview": f"consulted expert: {expert.name}"},
                }
                execution_plan = advance_execution_plan(
                    execution_plan,
                    event_type="handoff_success",
                    payload=payload,
                )
                execution_artifacts = record_execution_artifact(
                    execution_artifacts,
                    artifact_type="handoff",
                    payload=payload,
                )
            else:
                messages.append({
                    "role": "tool",
                    "name": "transfer_to_agent",
                    "content": f"Expert Error: target expert '{tid}' unavailable.",
                    "tool_call_id": tc["id"]
                })
                execution_plan = advance_execution_plan(
                    execution_plan,
                    event_type="handoff_error",
                    payload={"agent_id": tid, "status": "error", "error": "target expert unavailable", "tool_call_id": tc.get("id")},
                )
        except Exception as ee:
            logger.error(f"[HandoffNode] Handoff failed: {ee}")
            messages.append({
                "role": "tool",
                "name": "transfer_to_agent",
                "content": f"Expert Error: {ee}",
                "tool_call_id": tc["id"]
            })
            execution_plan = advance_execution_plan(
                execution_plan,
                event_type="handoff_error",
                payload={"status": "error", "error": str(ee), "tool_call_id": tc.get("id")},
            )

    await callback.emit(
        f"data: {json.dumps(build_task_runtime_update_event(task_frame=task_frame, execution_plan=execution_plan, execution_artifacts=execution_artifacts), ensure_ascii=False, default=str)}\n\n"
    )
    await persist_task_runtime_state(
        db,
        state.get("current_msg_id"),
        task_frame=task_frame,
        execution_plan=execution_plan,
        execution_artifacts=execution_artifacts,
    )

    return {
        "messages": messages,
        "current_agent_id": new_agent_id,
        "current_agent_profile": new_agent_profile,
        "called_expert_ids": called_expert_ids,
        "iter_text": "",
        "pending_tool_calls": [],
        "pending_delegate_type": "expert",
        "execution_plan": execution_plan,
        "execution_artifacts": execution_artifacts,
    }
