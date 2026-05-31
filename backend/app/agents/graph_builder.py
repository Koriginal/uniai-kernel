"""
UniAI Kernel — LangGraph 对话图编译器

将所有图节点和路由逻辑编译为可执行的 StateGraph。
这是系统的核心调度引擎，替代原 agent_service.py 中的 while 循环。

图结构：
    START → context_node → task_planner_node → agent_node
                                ├──[有 tool_calls，含 Handoff] → handoff_node → agent_node
                                ├──[有 tool_calls，含 Invoke]  → orchestrator_invoke_node → agent_node
                                ├──[有 tool_calls，无 Handoff] → tool_executor_node → agent_node
                                ├──[无 tool_calls，是专家]     → synthesize_node → agent_node
                                └──[无 tool_calls，是主控]     → task_evaluator_node → END
"""
import logging
import time
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import RunnableConfig
from app.core.graph_state import AgentGraphState

from app.agents.nodes import (
    context_node,
    task_planner_node,
    task_evaluator_node,
    agent_node,
    tool_executor_node,
    handoff_node,
    orchestrator_invoke_node,
    synthesize_node,
)
from app.agents.graph_telemetry import telemetry
from app.agents.pg_checkpointer import create_pg_checkpointer
from app.agents.auto_heal import auto_heal
from app.agents.adaptive_router import router

logger = logging.getLogger(__name__)


def _plan_summary(plan: dict | None) -> dict:
    if not isinstance(plan, dict):
        return {}
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    return {
        "status": plan.get("status"),
        "current_step": plan.get("current_step"),
        "step_count": len(steps),
        "completed_steps": len([step for step in steps if isinstance(step, dict) and step.get("status") == "completed"]),
        "blocked_steps": len([step for step in steps if isinstance(step, dict) and step.get("status") == "blocked"]),
        "failed_steps": len([step for step in steps if isinstance(step, dict) and step.get("status") == "failed"]),
    }


def _node_input_summary(state: dict) -> dict:
    task_frame = state.get("task_frame") if isinstance(state.get("task_frame"), dict) else {}
    return {
        "message_count": len(state.get("messages") or []),
        "pending_tool_calls": len(state.get("pending_tool_calls") or []),
        "current_agent_id": state.get("current_agent_id"),
        "iteration_count": state.get("iteration_count"),
        "task_kind": task_frame.get("kind"),
        "plan": _plan_summary(state.get("execution_plan")),
        "artifact_count": len(state.get("execution_artifacts") or []),
        "repair_count": state.get("task_repair_count") or 0,
        "pending_repair": bool(state.get("pending_repair")),
    }


def _node_output_summary(before: dict, result: dict | None) -> dict:
    result = result if isinstance(result, dict) else {}
    after = {**before, **result}
    updated_keys = sorted([key for key in result.keys() if not key.startswith("_")])
    text = result.get("iter_text")
    evaluation = after.get("task_evaluation") if isinstance(after.get("task_evaluation"), dict) else {}
    return {
        "updated_keys": updated_keys[:16],
        "message_count": len(after.get("messages") or []),
        "message_delta": len(after.get("messages") or []) - len(before.get("messages") or []),
        "pending_tool_calls": len(after.get("pending_tool_calls") or []),
        "iter_text_chars": len(text or "") if isinstance(text, str) else None,
        "plan": _plan_summary(after.get("execution_plan")),
        "artifact_count": len(after.get("execution_artifacts") or []),
        "task_evaluation_status": evaluation.get("status"),
        "pending_repair": bool(after.get("pending_repair")),
    }


# ─────────────────────────────────────────────
# 路由函数（条件边）
# ─────────────────────────────────────────────

async def adaptive_route(state: AgentGraphState, config: RunnableConfig) -> str:
    """包装自适应路由器"""
    return await router.route(state, config)


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


def route_after_orchestrator_invoke(state: AgentGraphState, config: RunnableConfig) -> str:
    """
    子主控接手后，返回 agent_node 继续执行子应用编排。
    """
    return "agent"


def route_after_task_evaluator(state: AgentGraphState, config: RunnableConfig) -> str:
    """
    验收失败且仍有修复额度时，回到 agent 补执行；否则结束。
    """
    return "agent" if state.get("pending_repair") else END


# ─────────────────────────────────────────────
# 图编译器
# ─────────────────────────────────────────────

_compiled_graph = None  # 模块级单例，避免重复编译


def wrap_telemetry(node_func, name):
    """辅助函数：为节点包裹遥测记录与自愈逻辑"""
    async def wrapped(state, config):
        started_at = time.perf_counter()
        input_summary = _node_input_summary(state)
        # 1. 执行前自检与追踪
        heal_state = await auto_heal.pre_node_check(state, name)
        state.update(heal_state)
        input_summary = _node_input_summary(state)
        
        # ── 获取流式回调 (推送实时轨迹给前端) ──
        callback = config.get("configurable", {}).get("stream_callback")
        if callback:
            await callback.emit_node_event("start", name, {
                "status": "running",
                "input_summary": input_summary,
            })
        
        async with telemetry.trace_node(name, state, config):
            try:
                result = await node_func(state, config)
                # 2. 执行成功后登记
                success_state = await auto_heal.post_node_success(state, name)
                output_summary = _node_output_summary(
                    state,
                    {**(result or {}), **(success_state or {})} if isinstance(result, dict) else success_state,
                )
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                
                # 推送结束事件
                if callback:
                    await callback.emit_node_event("end", name, {
                        "status": "success",
                        "duration_ms": duration_ms,
                        "input_summary": input_summary,
                        "output_summary": output_summary,
                    })
                
                if result and isinstance(result, dict):
                    result.update(success_state)
                return result
            except Exception as e:
                # 3. 故障处理
                error_state = await auto_heal.handle_error(state, name, e)
                state.update(error_state)
                
                # 推送错误事件
                if callback:
                    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                    await callback.emit_node_event("end", name, {
                        "status": "error", 
                        "message": str(e),
                        "duration_ms": duration_ms,
                        "input_summary": input_summary,
                        "output_summary": _node_output_summary(state, error_state),
                    })
                raise e
    return wrapped


async def build_conversation_graph():
    """
    编译并返回对话状态图（单例模式）。

    首次调用时编译图并挂载 MemorySaver checkpointer；
    后续调用直接返回已编译的图。
    """
    global _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph

    workflow = StateGraph(AgentGraphState)

    # ── 注册节点 (带遥测包裹) ──
    workflow.add_node("context", wrap_telemetry(context_node, "context"))
    workflow.add_node("task_planner", wrap_telemetry(task_planner_node, "task_planner"))
    workflow.add_node("task_evaluator", wrap_telemetry(task_evaluator_node, "task_evaluator"))
    workflow.add_node("agent", wrap_telemetry(agent_node, "agent"))
    workflow.add_node("tool_executor", wrap_telemetry(tool_executor_node, "tool_executor"))
    workflow.add_node("handoff", wrap_telemetry(handoff_node, "handoff"))
    workflow.add_node("orchestrator_invoke", wrap_telemetry(orchestrator_invoke_node, "orchestrator_invoke"))
    workflow.add_node("synthesize", wrap_telemetry(synthesize_node, "synthesize"))

    # ── 固定边 ──
    workflow.set_entry_point("context")
    workflow.add_edge("context", "task_planner")
    workflow.add_edge("task_planner", "agent")

    # ── 条件边：agent 出口 (自适应路由) ──
    workflow.add_conditional_edges(
        "agent",
        adaptive_route,
        {
            "handoff": "handoff",
            "orchestrator_invoke": "orchestrator_invoke",
            "tool_executor": "tool_executor",
            "synthesize": "synthesize",
            "task_evaluator": "task_evaluator",
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

    workflow.add_conditional_edges(
        "orchestrator_invoke",
        route_after_orchestrator_invoke,
        {"agent": "agent"}
    )

    # ── synthesize 后回 agent（让主控做最终收尾） ──
    workflow.add_edge("synthesize", "agent")
    workflow.add_conditional_edges(
        "task_evaluator",
        route_after_task_evaluator,
        {"agent": "agent", END: END}
    )

    # ── 挂载 PostgreSQL Checkpointer (阶段2：持久化) ──
    try:
        checkpointer = await create_pg_checkpointer()
    except Exception as e:
        logger.warning(f"[GraphBuilder] Fallback to MemorySaver due to: {e}")
        checkpointer = MemorySaver()
        
    _compiled_graph = workflow.compile(checkpointer=checkpointer)

    logger.info("[GraphBuilder] ✅ Conversation graph compiled successfully")
    logger.info(f"[GraphBuilder] Graph nodes: {list(workflow.nodes.keys())}")

    return _compiled_graph


async def get_graph_mermaid() -> str:
    """返回当前图的 Mermaid 表示，用于前端可视化"""
    graph = await build_conversation_graph()
    try:
        return graph.get_graph().draw_mermaid()
    except Exception as e:
        logger.warning(f"[GraphBuilder] Mermaid export failed: {e}")
        return ""
