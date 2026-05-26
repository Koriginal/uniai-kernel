"""
图节点：任务理解与执行计划

该节点把用户请求转成结构化 task_frame 和 execution_plan。
后续 agent/tool/handoff 节点都从 state 读取这份运行时状态，而不是只依赖
System Prompt 中的几段说明。
"""
import json
import logging
from typing import Any

from langgraph.types import RunnableConfig

from app.agents.task_runtime import (
    build_execution_plan,
    build_task_frame,
    latest_user_text_from_state,
)
from app.core.graph_state import AgentGraphState
from app.core.plugins import registry
from app.models.message import ChatMessage

logger = logging.getLogger(__name__)


async def task_planner_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    c = config["configurable"]
    callback = c.get("stream_callback")
    db = c.get("db")
    current_msg_id = state.get("current_msg_id")

    query = latest_user_text_from_state(state)
    available_tools = [tool.metadata.name for tool in registry.get_all_actions()]
    task_frame = build_task_frame(
        query=query,
        semantic_frame=state.get("semantic_frame") or {},
        semantic_slots=state.get("semantic_slots") or {},
        agent_profile=state.get("current_agent_profile") or {},
    )
    execution_plan = build_execution_plan(
        task_frame=task_frame,
        available_tools=available_tools,
        enable_swarm=bool(c.get("enable_swarm", True)),
    )

    event = {
        "type": "task_runtime",
        "task_frame": _compact_task_frame(task_frame),
        "execution_plan": execution_plan,
    }

    if callback:
        await callback.emit(f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n")

    if db and current_msg_id:
        await _persist_task_runtime(db, current_msg_id, event)

    return {
        "task_frame": task_frame,
        "execution_plan": execution_plan,
        "execution_artifacts": [],
    }


def _compact_task_frame(task_frame: dict[str, Any]) -> dict[str, Any]:
    compact = dict(task_frame)
    goal = compact.get("user_goal")
    if isinstance(goal, str) and len(goal) > 800:
        compact["user_goal"] = goal[:800] + "..."
    return compact


async def _persist_task_runtime(db, message_id: str, event: dict[str, Any]) -> None:
    try:
        msg = await db.get(ChatMessage, message_id)
        if not msg:
            return
        runtime_events = dict(msg.runtime_events or {})
        runtime_events["task_runtime"] = event
        msg.runtime_events = runtime_events
        db.add(msg)
        await db.commit()
    except Exception as exc:
        logger.debug(f"[TaskPlannerNode] persist task runtime failed: {exc}", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            logger.debug("[TaskPlannerNode] rollback failed", exc_info=True)
