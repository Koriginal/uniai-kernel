"""
图节点：任务验收

主控准备结束前执行一次确定性验收。它不替模型重写答案，
只根据任务框架、执行计划、运行产物和消息历史给出完成判定。
"""
import json
import logging

from langgraph.types import RunnableConfig

from app.agents.task_runtime import (
    build_task_runtime_update_event,
    build_repair_message,
    evaluate_task_completion,
    persist_task_runtime_state,
    reopen_plan_for_repair,
    should_repair_task,
)
from app.core.graph_state import AgentGraphState

logger = logging.getLogger(__name__)


async def task_evaluator_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    c = config["configurable"]
    callback = c.get("stream_callback")
    db = c.get("db")
    current_msg_id = state.get("current_msg_id")

    task_frame = state.get("task_frame") or {}
    execution_plan = dict(state.get("execution_plan") or {})
    execution_artifacts = list(state.get("execution_artifacts") or [])
    task_repair_count = int(state.get("task_repair_count") or 0)
    max_task_repairs = int(c.get("max_task_repairs", 1))
    task_evaluation = evaluate_task_completion(
        task_frame=task_frame,
        execution_plan=execution_plan,
        execution_artifacts=execution_artifacts,
        messages=state.get("messages") or [],
        assistant_text=state.get("total_assistant_content") or state.get("iter_text") or "",
    )

    if execution_plan:
        if task_evaluation["status"] == "passed":
            execution_plan["status"] = "completed"
        elif task_evaluation["status"] == "warning":
            execution_plan["status"] = "completed_with_warnings"
        else:
            execution_plan["status"] = "failed"
        execution_plan["evaluation_status"] = task_evaluation["status"]

    should_repair = should_repair_task(
        task_evaluation,
        repair_count=task_repair_count,
        max_repairs=max_task_repairs,
    )
    messages = list(state.get("messages") or [])
    if should_repair:
        execution_plan = reopen_plan_for_repair(execution_plan, task_evaluation) or execution_plan
        messages.append(
            build_repair_message(
                task_frame=task_frame,
                task_evaluation=task_evaluation,
            )
        )
        task_repair_count += 1

    event = {
        "type": "task_evaluation",
        "task_id": task_frame.get("task_id"),
        "evaluation": task_evaluation,
        "repair_scheduled": should_repair,
        "repair_count": task_repair_count,
    }
    if callback:
        await callback.emit(f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n")
        await callback.emit(
            f"data: {json.dumps(build_task_runtime_update_event(task_frame=task_frame, execution_plan=execution_plan, execution_artifacts=execution_artifacts, task_evaluation=task_evaluation), ensure_ascii=False, default=str)}\n\n"
        )

    await persist_task_runtime_state(
        db,
        current_msg_id,
        task_frame=task_frame,
        execution_plan=execution_plan,
        execution_artifacts=execution_artifacts,
        task_evaluation=task_evaluation,
    )

    return {
        "messages": messages,
        "execution_plan": execution_plan,
        "task_evaluation": task_evaluation,
        "task_repair_count": task_repair_count,
        "pending_repair": should_repair,
    }
