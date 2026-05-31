"""
图节点：工具执行

对应原 agent_service.py L446-458 的普通工具执行逻辑。
执行 pending_tool_calls 中的所有普通工具（排除 transfer_to_agent）。
"""
import json
import logging
import time
from typing import Any
from langgraph.types import RunnableConfig
from app.core.graph_state import AgentGraphState
from app.core.plugins import registry
from app.agents.task_runtime import (
    advance_execution_plan,
    build_task_runtime_update_event,
    persist_task_runtime_state,
    record_execution_artifact,
    validate_tool_against_plan,
)
from app.models.message import ChatMessage
from app.ontology.runtime import ONTOLOGY_AGENT_TOOL_NAMES, ontology_runtime
from app.services.audit_service import audit_service

logger = logging.getLogger(__name__)

SENSITIVE_ARG_KEYS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "private_key",
)


def _redact_tool_args(value: Any) -> Any:
    """Return a JSON-safe copy with obvious credentials removed before streaming/auditing."""
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(sensitive in key_text for sensitive in SENSITIVE_ARG_KEYS):
                redacted[key] = "***"
            else:
                redacted[key] = _redact_tool_args(item)
        return redacted
    if isinstance(value, list):
        return [_redact_tool_args(item) for item in value]
    return value


def _summarize_tool_result(result: Any, max_chars: int = 700) -> dict:
    """Create a compact result preview for runtime UI without flooding the chat stream."""
    result_type = type(result).__name__
    if isinstance(result, (dict, list)):
        preview = json.dumps(result, ensure_ascii=False, default=str)
    else:
        preview = str(result)

    truncated = len(preview) > max_chars
    if truncated:
        preview = preview[:max_chars] + "..."
    return {
        "result_type": result_type,
        "preview": preview,
        "truncated": truncated,
    }


def _get_tool_metadata(func_name: str) -> dict:
    action = registry.get_action(func_name)
    if not action:
        return {
            "tool_name": func_name,
            "tool_label": func_name,
            "category": "unknown",
        }
    metadata = action.metadata
    return {
        "tool_name": metadata.name,
        "tool_label": metadata.label or metadata.name,
        "category": metadata.category or "tool",
        "version": metadata.version,
    }


def _is_tool_allowed_by_policy(func_name: str, runtime_policy: dict | None) -> tuple[bool, str | None]:
    """Defense-in-depth guard. The model node filters tools, this node enforces execution."""
    policy = runtime_policy or {}
    if policy.get("allow_tools") is False:
        return False, "当前智能体运行策略禁止执行工具"
    if func_name == "web_search" and policy.get("allow_web_search") is False:
        return False, "当前智能体运行策略禁止联网检索"
    return True, None


async def _emit_tool_runtime(callback: Any, payload: dict) -> None:
    event = {"type": "tool_runtime", **payload}
    await callback.emit(f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n")


async def _audit_tool_runtime(config_data: dict, *, status: str, payload: dict) -> None:
    """Persist tool execution audit without letting audit failures break the chat flow."""
    db = config_data.get("db")
    user_id = config_data.get("user_id")
    if not db or not user_id:
        return
    try:
        result = payload.get("result") or {}
        await audit_service.log_action(
            db,
            user_id=user_id,
            session_id=config_data.get("session_id"),
            agent_id=config_data.get("current_agent_id") or payload.get("agent_id"),
            action_name=f"tool.{payload.get('tool_name') or 'unknown'}",
            status=status,
            input_params={
                "tool_call_id": payload.get("tool_call_id"),
                "tool_name": payload.get("tool_name"),
                "tool_label": payload.get("tool_label"),
                "category": payload.get("category"),
                "arguments": payload.get("arguments"),
                "error": payload.get("error"),
                "plan_step_id": payload.get("plan_step_id"),
                "policy_decision": payload.get("policy_decision"),
                "policy_reason": payload.get("policy_reason"),
            },
            output_result=result.get("preview") or payload.get("error"),
            duration_ms=float(payload.get("duration_ms") or 0),
        )
    except Exception:
        logger.debug("[ToolExecutor] Tool audit failed", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            logger.debug("[ToolExecutor] Failed to rollback audit error", exc_info=True)


async def _persist_tool_runtime_event(config_data: dict, state: AgentGraphState, payload: dict) -> None:
    """Attach compact tool runtime events to the assistant message for history replay."""
    db = config_data.get("db")
    msg_id = state.get("current_msg_id")
    if not db or not msg_id:
        return
    try:
        msg_to_update = await db.get(ChatMessage, msg_id)
        if not msg_to_update:
            return
        runtime_events = dict(msg_to_update.runtime_events or {})
        tool_events = list(runtime_events.get("tool_runtime_events") or [])
        event_index = next(
            (
                idx
                for idx, event in enumerate(tool_events)
                if event.get("tool_call_id") == payload.get("tool_call_id")
            ),
            -1,
        )
        compact_payload = {
            key: payload.get(key)
            for key in (
                "tool_call_id",
                "tool_name",
                "tool_label",
                "category",
                "version",
                "phase",
                "status",
                "duration_ms",
                "arguments",
                "result",
                "error",
                "agent_id",
                "plan_step_id",
                "policy_decision",
                "policy_reason",
            )
            if key in payload
        }
        if event_index >= 0:
            tool_events[event_index] = {**tool_events[event_index], **compact_payload}
        else:
            tool_events.append(compact_payload)
        runtime_events["tool_runtime_events"] = tool_events[-20:]
        msg_to_update.runtime_events = runtime_events
        db.add(msg_to_update)
        await db.commit()
    except Exception:
        logger.debug("[ToolExecutor] Tool runtime event persist failed", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            logger.debug("[ToolExecutor] Failed to rollback runtime event persist error", exc_info=True)


def inject_runtime_tool_args(func_name: str, args: dict, config_data: dict, agent_profile: dict | None) -> dict:
    """Inject trusted runtime context into tools that should not rely on LLM-supplied identity."""
    if func_name not in ONTOLOGY_AGENT_TOOL_NAMES:
        return args

    patched = dict(args or {})
    ontology_config = ontology_runtime.normalize_config((agent_profile or {}).get("ontology_config") or {})
    if config_data.get("user_id"):
        patched["user_id"] = config_data["user_id"]
    patched["is_admin"] = bool(config_data.get("is_admin", False))
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
    runtime_policy = (agent_profile or {}).get("runtime_policy") or {}
    c["current_agent_id"] = state.get("current_agent_id")
    messages = list(state["messages"])
    pending_tool_calls = state["pending_tool_calls"]
    iter_text = state["iter_text"]
    task_frame = state.get("task_frame") or {}
    execution_plan = state.get("execution_plan") or {}
    execution_artifacts = list(state.get("execution_artifacts") or [])

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
        tool_call_id = tc.get("id")
        tool_meta = _get_tool_metadata(func_name)
        started_at = time.perf_counter()
        parsed_args: dict = {}
        plan_policy: dict = {}
        try:
            agent_name = agent_profile.get("name", "Assistant") if agent_profile else "Assistant"
            await callback.emit(
                f"data: {json.dumps({'type': 'status', 'state': 'active', 'agentName': agent_name, 'content': f'正在执行 {func_name}...'})}\n\n"
            )
            raw_args = tc["function"].get("arguments") or "{}"
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            if not isinstance(args, dict):
                raise ValueError("Tool arguments must be a JSON object")
            parsed_args = inject_runtime_tool_args(func_name, args, c, agent_profile)
            is_allowed, blocked_reason = _is_tool_allowed_by_policy(func_name, runtime_policy)
            plan_policy = validate_tool_against_plan(
                tool_name=func_name,
                tool_metadata=tool_meta,
                task_frame=task_frame,
                execution_plan=execution_plan,
            )
            if is_allowed and not plan_policy.get("allowed", True):
                is_allowed = False
                blocked_reason = plan_policy.get("reason") or "工具调用不符合当前执行计划"
            execution_plan = advance_execution_plan(
                execution_plan,
                event_type="tool_start",
                payload={
                    "tool_name": func_name,
                    "tool_call_id": tool_call_id,
                    "plan_step_id": plan_policy.get("plan_step_id"),
                    "policy_decision": plan_policy.get("decision"),
                    "policy_reason": plan_policy.get("reason"),
                },
            )
            await _emit_tool_runtime(callback, {
                **tool_meta,
                "tool_call_id": tool_call_id,
                "phase": "start",
                "status": "running",
                "arguments": _redact_tool_args(parsed_args),
                "plan_step_id": plan_policy.get("plan_step_id"),
                "policy_decision": plan_policy.get("decision"),
                "policy_reason": plan_policy.get("reason"),
            })
            if not is_allowed:
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                runtime_payload = {
                    **tool_meta,
                    "tool_call_id": tool_call_id,
                    "phase": "end",
                    "status": "blocked",
                    "duration_ms": duration_ms,
                    "arguments": _redact_tool_args(parsed_args),
                    "error": blocked_reason,
                    "agent_id": state.get("current_agent_id"),
                    "plan_step_id": plan_policy.get("plan_step_id"),
                    "policy_decision": plan_policy.get("decision"),
                    "policy_reason": plan_policy.get("reason"),
                }
                await _emit_tool_runtime(callback, runtime_payload)
                execution_plan = advance_execution_plan(
                    execution_plan,
                    event_type="tool_blocked",
                    payload=runtime_payload,
                )
                execution_artifacts = record_execution_artifact(
                    execution_artifacts,
                    artifact_type="tool_result",
                    payload=runtime_payload,
                )
                await _emit_task_runtime_update(callback, c, state, task_frame, execution_plan, execution_artifacts)
                await _persist_tool_runtime_event(c, state, runtime_payload)
                await _audit_tool_runtime(c, status="blocked", payload=runtime_payload)
                messages.append({
                    "role": "tool",
                    "name": func_name,
                    "content": f"Tool Blocked: {blocked_reason}",
                    "tool_call_id": tool_call_id
                })
                continue

            res = await registry.execute_action(func_name, **parsed_args)
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            runtime_payload = {
                **tool_meta,
                "tool_call_id": tool_call_id,
                "phase": "end",
                "status": "success",
                "duration_ms": duration_ms,
                "arguments": _redact_tool_args(parsed_args),
                "result": _summarize_tool_result(res),
                "agent_id": state.get("current_agent_id"),
                "plan_step_id": plan_policy.get("plan_step_id"),
                "policy_decision": plan_policy.get("decision"),
                "policy_reason": plan_policy.get("reason"),
            }
            await _emit_tool_runtime(callback, runtime_payload)
            execution_plan = advance_execution_plan(
                execution_plan,
                event_type="tool_success",
                payload=runtime_payload,
            )
            execution_artifacts = record_execution_artifact(
                execution_artifacts,
                artifact_type="tool_result",
                payload=runtime_payload,
            )
            await _emit_task_runtime_update(callback, c, state, task_frame, execution_plan, execution_artifacts)
            await _persist_tool_runtime_event(c, state, runtime_payload)
            await _audit_tool_runtime(c, status="success", payload=runtime_payload)
            messages.append({
                "role": "tool",
                "name": func_name,
                "content": str(res),
                "tool_call_id": tool_call_id
            })
        except Exception as te:
            logger.error(f"[ToolExecutor] Tool '{func_name}' execution failed: {te}")
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            try:
                runtime_payload = {
                    **tool_meta,
                    "tool_call_id": tool_call_id,
                    "phase": "end",
                    "status": "error",
                    "duration_ms": duration_ms,
                    "arguments": _redact_tool_args(parsed_args),
                    "error": str(te),
                    "agent_id": state.get("current_agent_id"),
                    "plan_step_id": plan_policy.get("plan_step_id"),
                    "policy_decision": plan_policy.get("decision"),
                    "policy_reason": plan_policy.get("reason"),
                }
                await _emit_tool_runtime(callback, runtime_payload)
                execution_plan = advance_execution_plan(
                    execution_plan,
                    event_type="tool_error",
                    payload=runtime_payload,
                )
                execution_artifacts = record_execution_artifact(
                    execution_artifacts,
                    artifact_type="tool_result",
                    payload=runtime_payload,
                )
                await _emit_task_runtime_update(callback, c, state, task_frame, execution_plan, execution_artifacts)
                await _persist_tool_runtime_event(c, state, runtime_payload)
                await _audit_tool_runtime(c, status="error", payload=runtime_payload)
            except Exception:
                logger.debug("[ToolExecutor] Failed to emit tool_runtime error event", exc_info=True)
            messages.append({
                "role": "tool",
                "name": func_name,
                "content": f"Tool Error: {te}",
                "tool_call_id": tool_call_id
            })

    return {
        "messages": messages,
        "iter_text": "",  # 清空本轮文本，下一个 agent_node 重新开始
        "execution_plan": execution_plan,
        "execution_artifacts": execution_artifacts,
    }


async def _emit_task_runtime_update(
    callback: Any,
    config_data: dict,
    state: AgentGraphState,
    task_frame: dict,
    execution_plan: dict | None,
    execution_artifacts: list,
) -> None:
    await callback.emit(
        f"data: {json.dumps(build_task_runtime_update_event(task_frame=task_frame, execution_plan=execution_plan, execution_artifacts=execution_artifacts), ensure_ascii=False, default=str)}\n\n"
    )
    await persist_task_runtime_state(
        config_data.get("db"),
        state.get("current_msg_id"),
        task_frame=task_frame,
        execution_plan=execution_plan,
        execution_artifacts=execution_artifacts,
    )
