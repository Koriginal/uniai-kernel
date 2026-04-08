"""
UniAI Kernel — LangGraph 对话图编译器

将所有图节点和路由逻辑编译为可执行的 StateGraph。
这是系统的核心调度引擎，替代原 agent_service.py 中的 while 循环。

图结构：
    START → context_node → agent_node
                                ├──[有 tool_calls，含 Handoff] → handoff_node → agent_node
                                ├──[有 tool_calls，无 Handoff] → tool_executor_node → agent_node
                                ├──[无 tool_calls，是专家]     → synthesize_node → agent_node
                                └──[无 tool_calls，是主控]     → END
"""
import logging
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import RunnableConfig

from app.core.graph_state import AgentGraphState
from app.agents.nodes import (
    context_node,
    agent_node,
    tool_executor_node,
    handoff_node,
    synthesize_node,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 路由函数（条件边）
# ─────────────────────────────────────────────

def should_continue(state: AgentGraphState, config: RunnableConfig) -> str:
    """
    从 agent_node 出发的路由决策。

    决策树：
    1. 超过最大迭代次数 → END（防死循环）
    2. 有 pending_tool_calls：
       a. 包含 transfer_to_agent → handoff
       b. 仅普通工具 → tool_executor
    3. 无 tool_calls：
       a. 当前是专家（非 orchestrator）→ synthesize（归还主控）
       b. 当前是主控 → END（完成）
    """
    c = config.get("configurable", {})
    max_iter = c.get("max_iterations", 10)
    orchestrator_id = c.get("orchestrator_agent_id", "")

    # 防无限循环
    if state["iteration_count"] >= max_iter:
        logger.warning(f"[Router] Max iterations ({max_iter}) reached, forcing END")
        return END

    pending = state.get("pending_tool_calls", [])

    if pending:
        has_handoff = any(
            tc.get("function", {}).get("name") == "transfer_to_agent"
            for tc in pending
        )
        if has_handoff:
            return "handoff"
        return "tool_executor"

    # 无 tool_calls
    current_agent_id = state.get("current_agent_id", "")
    if current_agent_id != orchestrator_id:
        return "synthesize"

    return END


def route_after_tools(state: AgentGraphState, config: RunnableConfig) -> str:
    """
    工具执行完毕后，始终返回 agent_node 继续思考。
    （工具结果已追加到 messages，让 LLM 看到并给出下一步回应）
    """
    return "agent"


def route_after_handoff(state: AgentGraphState, config: RunnableConfig) -> str:
    """
    专家接手后，始终返回 agent_node 让专家开始思考。
    """
    return "agent"


# ─────────────────────────────────────────────
# 图编译器
# ─────────────────────────────────────────────

_compiled_graph = None  # 模块级单例，避免重复编译


def build_conversation_graph():
    """
    编译并返回对话状态图（单例模式）。

    首次调用时编译图并挂载 MemorySaver checkpointer；
    后续调用直接返回已编译的图。
    """
    global _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph

    workflow = StateGraph(AgentGraphState)

    # ── 注册节点 ──
    workflow.add_node("context", context_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tool_executor", tool_executor_node)
    workflow.add_node("handoff", handoff_node)
    workflow.add_node("synthesize", synthesize_node)

    # ── 固定边 ──
    workflow.set_entry_point("context")
    workflow.add_edge("context", "agent")

    # ── 条件边：agent 出口 ──
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "handoff": "handoff",
            "tool_executor": "tool_executor",
            "synthesize": "synthesize",
            END: END,
        }
    )

    # ── 工具执行后回 agent ──
    workflow.add_conditional_edges(
        "tool_executor",
        route_after_tools,
        {"agent": "agent"}
    )

    # ── 专家接手后回 agent ──
    workflow.add_conditional_edges(
        "handoff",
        route_after_handoff,
        {"agent": "agent"}
    )

    # ── synthesize 后回 agent（让主控做最终收尾） ──
    workflow.add_edge("synthesize", "agent")

    # ── 挂载 MemorySaver（阶段1：内存 checkpoint） ──
    checkpointer = MemorySaver()
    _compiled_graph = workflow.compile(checkpointer=checkpointer)

    logger.info("[GraphBuilder] ✅ Conversation graph compiled successfully")
    logger.info(f"[GraphBuilder] Graph nodes: {list(workflow.nodes.keys())}")

    return _compiled_graph


def get_graph_mermaid() -> str:
    """返回当前图的 Mermaid 表示，用于前端可视化"""
    graph = build_conversation_graph()
    try:
        return graph.get_graph().draw_mermaid()
    except Exception as e:
        logger.warning(f"[GraphBuilder] Mermaid export failed: {e}")
        return ""
