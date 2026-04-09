"""
图节点：工具执行

对应原 agent_service.py L446-458 的普通工具执行逻辑。
执行 pending_tool_calls 中的所有普通工具（排除 transfer_to_agent）。
"""
import json
import logging
from langgraph.types import RunnableConfig
from app.core.graph_state import AgentGraphState
from app.core.plugins import registry

logger = logging.getLogger(__name__)


async def tool_executor_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """
    工具执行节点：并行执行所有普通工具调用。

    transfer_to_agent 由 router 分流到 handoff_node，此节点只处理常规工具。
    """
    c = config["configurable"]
    callback = c["stream_callback"]
    agent_profile = state["current_agent_profile"]
    messages = list(state["messages"])
    pending_tool_calls = state["pending_tool_calls"]
    iter_text = state["iter_text"]

    # 先将 assistant 消息（含 tool_calls）追加到消息列表
    tool_calls_for_msg = [tc for tc in pending_tool_calls if tc.get("function", {}).get("name") != "transfer_to_agent"]
    all_tc_in_buffer = list(pending_tool_calls)

    messages.append({
        "role": "assistant",
        "content": iter_text or None,
        "tool_calls": all_tc_in_buffer
    })

    # 执行每一个普通工具
    for tc in tool_calls_for_msg:
        func_name = tc["function"]["name"]
        try:
            agent_name = agent_profile.get("name", "Assistant") if agent_profile else "Assistant"
            await callback.emit(
                f"data: {json.dumps({'type': 'status', 'state': 'active', 'agentName': agent_name, 'content': f'正在执行 {func_name}...'})}\n\n"
            )
            raw_args = tc["function"].get("arguments") or "{}"
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            if not isinstance(args, dict):
                raise ValueError("Tool arguments must be a JSON object")
            res = await registry.execute_action(func_name, **args)
            messages.append({
                "role": "tool",
                "name": func_name,
                "content": str(res),
                "tool_call_id": tc["id"]
            })
        except Exception as te:
            logger.error(f"[ToolExecutor] Tool '{func_name}' execution failed: {te}")
            messages.append({
                "role": "tool",
                "name": func_name,
                "content": f"Tool Error: {te}",
                "tool_call_id": tc["id"]
            })

    return {
        "messages": messages,
        "iter_text": "",  # 清空本轮文本，下一个 agent_node 重新开始
    }
