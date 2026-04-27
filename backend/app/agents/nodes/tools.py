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
from app.ontology.runtime import ONTOLOGY_AGENT_TOOL_NAMES, ontology_runtime

logger = logging.getLogger(__name__)


def inject_runtime_tool_args(func_name: str, args: dict, config_data: dict, agent_profile: dict | None) -> dict:
    """Inject trusted runtime context into tools that should not rely on LLM-supplied identity."""
    if func_name not in ONTOLOGY_AGENT_TOOL_NAMES:
        return args

    patched = dict(args or {})
    ontology_config = ontology_runtime.normalize_config((agent_profile or {}).get("ontology_config") or {})
    if config_data.get("user_id"):
        patched["user_id"] = config_data["user_id"]
    if ontology_config.get("space_id") and not patched.get("space_id"):
        patched["space_id"] = ontology_config["space_id"]
    return patched


async def tool_executor_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """
    工具执行节点：并行执行所有普通工具调用。

    transfer_to_agent / invoke_orchestrator 由 router 分流到 handoff_node，此节点只处理常规工具。
    """
    c = config["configurable"]
    callback = c["stream_callback"]
    agent_profile = state["current_agent_profile"]
    messages = list(state["messages"])
    pending_tool_calls = state["pending_tool_calls"]
    iter_text = state["iter_text"]

    # 先将 assistant 消息（含 tool_calls）追加到消息列表
    tool_calls_for_msg = [
        tc for tc in pending_tool_calls
        if tc.get("function", {}).get("name") not in {"transfer_to_agent", "invoke_orchestrator"}
    ]
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
            args = inject_runtime_tool_args(func_name, args, c, agent_profile)
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
