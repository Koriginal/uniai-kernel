"""
Task runtime primitives for the conversation graph.

This module keeps task understanding and execution planning outside the prompt
text. The output is plain dict data so it can be stored in graph state,
streamed to the UI, audited, and later used by routers or tool policies.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any


REALTIME_KEYWORDS = {
    "今日", "今天", "最新", "当前", "实时", "现在", "刚刚",
    "价格", "汇率", "股价", "新闻", "公告", "政策",
    "today", "latest", "current", "realtime", "real-time", "price", "news",
}

CODING_KEYWORDS = {
    "代码", "实现", "修复", "报错", "测试", "接口", "模块", "重构", "仓库",
    "bug", "fix", "implement", "code", "test", "refactor", "api", "repo",
}

REVIEW_KEYWORDS = {
    "审核", "审查", "风控", "合规", "风险", "校验", "评估",
    "review", "risk", "compliance", "validate", "assess",
}

DOCUMENT_KEYWORDS = {
    "合同", "协议", "甲方", "乙方", "付款", "违约", "责任上限", "自动续约",
    "contract", "agreement", "payment terms", "liability", "termination",
}


def get_runtime_capability_catalog() -> list[dict[str, Any]]:
    """Return framework-level runtime capabilities exposed by the agent kernel."""
    return [
        {
            "id": "task_understanding",
            "label": "任务理解",
            "node": "task_planner",
            "state_fields": ["task_frame", "semantic_frame", "semantic_slots"],
            "events": ["task_runtime"],
            "description": "把用户输入转成任务类型、目标、约束、验收条件和风险标记。",
        },
        {
            "id": "execution_planning",
            "label": "执行拆解",
            "node": "task_planner",
            "state_fields": ["execution_plan"],
            "events": ["task_runtime"],
            "description": "按任务类型生成步骤、责任方、工具候选和完成标准。",
        },
        {
            "id": "execution_ledger",
            "label": "执行账本",
            "node": "agent/tool_executor/handoff/orchestrator_invoke/synthesize",
            "state_fields": ["execution_plan", "execution_artifacts"],
            "events": ["task_runtime_update", "tool_runtime"],
            "description": "节点执行时推进步骤状态，记录工具、专家和子主控产物。",
        },
        {
            "id": "task_evaluation",
            "label": "任务验收",
            "node": "task_evaluator",
            "state_fields": ["task_evaluation"],
            "events": ["task_evaluation", "task_runtime_update"],
            "description": "主控结束前按计划状态、产物和任务约束做确定性验收。",
        },
        {
            "id": "runtime_repair",
            "label": "运行时修复",
            "node": "task_evaluator -> agent",
            "state_fields": ["task_repair_count", "pending_repair", "execution_plan"],
            "events": ["task_evaluation", "task_runtime_update"],
            "config": ["max_task_repairs"],
            "description": "验收失败且仍有额度时，重开缺口步骤并回到 agent 补执行。",
        },
    ]


def _stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _contains_any(text: str, keywords: set[str]) -> bool:
    lower = (text or "").lower()
    return any(item in lower for item in keywords)


def _extract_latest_user_text(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages or []):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            return " ".join([part for part in parts if part]).strip()
    return ""


def latest_user_text_from_state(state: dict[str, Any]) -> str:
    return _extract_latest_user_text(state.get("messages", []))


def classify_task(query: str, semantic_frame: dict[str, Any] | None = None) -> str:
    """Return a coarse task kind used by planning and routing."""
    frame_kind = (semantic_frame or {}).get("intent") or (semantic_frame or {}).get("task_type")
    if isinstance(frame_kind, str) and frame_kind:
        normalized = frame_kind.lower()
        if normalized in {"workflow", "builder", "analysis"}:
            return normalized

    lower = (query or "").lower()
    review_hits = sum(1 for item in REVIEW_KEYWORDS if item in lower)
    doc_hits = sum(1 for item in DOCUMENT_KEYWORDS if item in lower)
    if review_hits >= 1 and doc_hits >= 1:
        return "business_review"
    if _contains_any(query, REALTIME_KEYWORDS):
        return "realtime_research"
    if _contains_any(query, CODING_KEYWORDS):
        return "engineering"
    if len(query) > 700 and doc_hits >= 2:
        return "business_review"
    return "general"


def build_task_frame(
    *,
    query: str,
    semantic_frame: dict[str, Any] | None,
    semantic_slots: dict[str, Any] | None,
    agent_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    task_kind = classify_task(query, semantic_frame)
    profile_policy = (agent_profile or {}).get("runtime_policy") or {}
    ontology_config = (agent_profile or {}).get("ontology_config") or {}
    requires_external_facts = task_kind == "realtime_research"
    requires_code_workspace = task_kind == "engineering"
    requires_governance = task_kind == "business_review" or bool(ontology_config.get("enabled"))

    return {
        "task_id": _stable_id("task", query),
        "kind": task_kind,
        "user_goal": query,
        "semantic_frame": semantic_frame or {},
        "semantic_slots": semantic_slots or {},
        "constraints": {
            "allow_tools": bool(profile_policy.get("allow_tools", True)),
            "allow_web_search": bool(profile_policy.get("allow_web_search", True)),
            "requires_external_facts": requires_external_facts,
            "requires_code_workspace": requires_code_workspace,
            "requires_governance": requires_governance,
        },
        "acceptance": _default_acceptance(task_kind),
        "risk_flags": _risk_flags(query, task_kind, profile_policy),
    }


def build_execution_plan(
    *,
    task_frame: dict[str, Any],
    available_tools: list[str],
    enable_swarm: bool,
) -> dict[str, Any]:
    kind = task_frame.get("kind") or "general"
    tool_set = set(available_tools or [])
    steps: list[dict[str, Any]]

    if kind == "realtime_research":
        steps = [
            _step("understand", "确认用户要查的对象、时间范围和口径", "orchestrator"),
            _step("retrieve", "调用 web_search 获取当前信息和来源", "tool", ["web_search"] if "web_search" in tool_set else []),
            _step("synthesize", "按时间和来源合并结果，标注不确定项", "orchestrator"),
        ]
    elif kind == "business_review":
        ontology_tools = [name for name in available_tools if name.startswith("ontology_")]
        steps = [
            _step("extract", "识别文本中的主体、条款、金额、期限和义务", "orchestrator"),
            _step("evaluate", "按本体映射和规则评估风险；没有绑定本体时给人工审阅结论", "tool", ontology_tools),
            _step("explain", "输出命中规则、证据、缺失字段和下一步动作", "orchestrator"),
        ]
    elif kind == "engineering":
        steps = [
            _step("inspect", "读取仓库结构、相关模块和现有测试", "orchestrator"),
            _step("change", "按现有边界修改代码或配置", "orchestrator"),
            _step("verify", "运行最小必要测试并记录结果", "tool"),
        ]
    else:
        steps = [
            _step("understand", "澄清目标、输入、边界和输出格式", "orchestrator"),
            _step("solve", "基于上下文、记忆和可用工具完成任务", "orchestrator"),
            _step("respond", "给出结果、依据和剩余风险", "orchestrator"),
        ]

    if enable_swarm and kind in {"engineering", "analysis", "workflow"}:
        steps.insert(1, _step("delegate", "必要时选择一个专家处理明确子任务", "expert"))

    return {
        "plan_id": _stable_id("plan", f"{task_frame.get('task_id')}:{kind}:{len(steps)}"),
        "task_id": task_frame.get("task_id"),
        "status": "planned",
        "steps": steps,
        "current_step": steps[0]["id"] if steps else None,
        "done_criteria": task_frame.get("acceptance") or [],
    }


def build_runtime_prompt_block(task_frame: dict[str, Any] | None, execution_plan: dict[str, Any] | None) -> str:
    if not task_frame or not execution_plan:
        return ""
    step_lines = []
    for idx, step in enumerate(execution_plan.get("steps") or [], start=1):
        tools = step.get("tool_candidates") or []
        tool_text = f" tools={tools}" if tools else ""
        step_lines.append(f"{idx}. {step.get('id')}: {step.get('title')} owner={step.get('owner')}{tool_text}")

    acceptance = task_frame.get("acceptance") or []
    risks = task_frame.get("risk_flags") or []
    return (
        "\n\n[TASK RUNTIME CONTRACT]\n"
        f"task_id: {task_frame.get('task_id')}\n"
        f"kind: {task_frame.get('kind')}\n"
        f"user_goal: {_compact_text(task_frame.get('user_goal') or '', 900)}\n"
        "execution_plan:\n"
        + "\n".join(step_lines)
        + "\nacceptance:\n"
        + "\n".join([f"- {item}" for item in acceptance])
        + ("\nrisk_flags:\n" + "\n".join([f"- {item}" for item in risks]) if risks else "")
        + "\nRules: Follow the execution_plan. Do not skip retrieval, verification, or governance steps when the plan requires them."
    )


def advance_execution_plan(
    execution_plan: dict[str, Any] | None,
    *,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Advance plan state after graph node events.

    The plan remains advisory for now, but every graph node can mark the step it
    affected. This gives routing, audit, and UI a shared execution ledger.
    """
    if not execution_plan:
        return execution_plan

    plan = {**execution_plan}
    steps = [dict(step) for step in plan.get("steps") or []]
    payload = payload or {}
    if not steps:
        return plan

    target_id = _resolve_step_id(steps, event_type, payload, plan.get("current_step"))
    status = _status_for_event(event_type)
    if not target_id or not status:
        return plan

    found_index = None
    for index, step in enumerate(steps):
        if step.get("id") == target_id:
            found_index = index
            step["status"] = status
            step["last_event"] = {
                "type": event_type,
                "summary": _event_summary(payload),
            }
            break

    if found_index is None:
        return plan

    plan["steps"] = steps
    if status == "in_progress":
        plan["current_step"] = target_id
        plan["status"] = "running"
        return plan

    next_step = _next_open_step(steps, start_index=found_index)
    plan["current_step"] = next_step.get("id") if next_step else None
    plan["status"] = "completed" if next_step is None else "running"
    return plan


def record_execution_artifact(
    artifacts: list[dict[str, Any]] | None,
    *,
    artifact_type: str,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    items = list(artifacts or [])
    items.append(
        {
            "type": artifact_type,
            "status": payload.get("status"),
            "tool_call_id": payload.get("tool_call_id"),
            "tool_name": payload.get("tool_name"),
            "agent_id": payload.get("agent_id"),
            "preview": (payload.get("result") or {}).get("preview") or payload.get("error"),
            "metadata": {
                key: payload.get(key)
                for key in ("category", "duration_ms", "phase")
                if key in payload
            },
        }
    )
    return items[-30:]


async def persist_task_runtime_state(
    db: Any,
    message_id: str | None,
    *,
    task_frame: dict[str, Any] | None,
    execution_plan: dict[str, Any] | None,
    execution_artifacts: list[dict[str, Any]] | None,
    task_evaluation: dict[str, Any] | None = None,
) -> None:
    if not db or not message_id:
        return
    from app.models.message import ChatMessage

    try:
        msg = await db.get(ChatMessage, message_id)
        if not msg:
            return
        runtime_events = dict(msg.runtime_events or {})
        runtime_events["task_runtime"] = {
            "type": "task_runtime",
            "task_frame": task_frame,
            "execution_plan": execution_plan,
            "execution_artifacts": execution_artifacts or [],
            "task_evaluation": task_evaluation,
        }
        msg.runtime_events = runtime_events
        db.add(msg)
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass


def build_task_runtime_update_event(
    *,
    task_frame: dict[str, Any] | None,
    execution_plan: dict[str, Any] | None,
    execution_artifacts: list[dict[str, Any]] | None = None,
    task_evaluation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "task_runtime_update",
        "task_frame": task_frame,
        "execution_plan": execution_plan,
        "execution_artifacts": execution_artifacts or [],
        "task_evaluation": task_evaluation,
    }


def should_repair_task(
    task_evaluation: dict[str, Any] | None,
    *,
    repair_count: int,
    max_repairs: int,
) -> bool:
    if not task_evaluation:
        return False
    return task_evaluation.get("status") == "failed" and repair_count < max_repairs


def build_repair_message(
    *,
    task_frame: dict[str, Any] | None,
    task_evaluation: dict[str, Any],
) -> dict[str, Any]:
    frame = task_frame or {}
    missing = task_evaluation.get("missing_requirements") or []
    checks = task_evaluation.get("checks") or []
    failed_checks = [
        check.get("id")
        for check in checks
        if check.get("status") == "failed"
    ]
    return {
        "role": "user",
        "content": (
            "[RUNTIME REPAIR REQUEST]\n"
            "The previous answer did not satisfy the task runtime checks.\n"
            f"Original user goal: {frame.get('user_goal') or ''}\n"
            f"Missing requirements: {', '.join(missing) if missing else 'none'}\n"
            f"Failed checks: {', '.join([item for item in failed_checks if item]) if failed_checks else 'none'}\n"
            "Repair only the missing parts. Use the required tool or evidence if a missing requirement asks for it, then answer the original user goal."
        ),
    }


def reopen_plan_for_repair(
    execution_plan: dict[str, Any] | None,
    task_evaluation: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not execution_plan:
        return execution_plan
    plan = {**execution_plan}
    steps = [dict(step) for step in plan.get("steps") or []]
    missing = set((task_evaluation or {}).get("missing_requirements") or [])

    target_id = None
    if "web_search_result" in missing:
        for step in steps:
            if "web_search" in (step.get("tool_candidates") or []) or step.get("owner") == "tool":
                target_id = step.get("id")
                step["status"] = "pending"
                step["last_event"] = {
                    "type": "repair_required",
                    "summary": {"missing": "web_search_result"},
                }
                break
    if target_id is None:
        for step in steps:
            if step.get("status") in {"failed", "blocked", "pending", "in_progress"}:
                target_id = step.get("id")
                step["status"] = "pending"
                step["last_event"] = {
                    "type": "repair_required",
                    "summary": {"missing": list(missing)},
                }
                break
    if target_id is None and steps:
        target_id = steps[-1].get("id")
        steps[-1]["status"] = "pending"

    plan["steps"] = steps
    plan["current_step"] = target_id
    plan["status"] = "repairing"
    plan["evaluation_status"] = "repairing"
    return plan


def evaluate_task_completion(
    *,
    task_frame: dict[str, Any] | None,
    execution_plan: dict[str, Any] | None,
    execution_artifacts: list[dict[str, Any]] | None,
    messages: list[dict[str, Any]] | None,
    assistant_text: str | None,
) -> dict[str, Any]:
    frame = task_frame or {}
    plan = execution_plan or {}
    artifacts = execution_artifacts or []
    checks: list[dict[str, Any]] = []
    missing: list[str] = []

    response_present = bool((assistant_text or "").strip())
    checks.append(
        {
            "id": "response_present",
            "status": "passed" if response_present else "failed",
            "detail": "assistant produced final text" if response_present else "assistant response is empty",
        }
    )
    if not response_present:
        missing.append("final_response")

    steps = plan.get("steps") or []
    failed_steps = [step for step in steps if step.get("status") == "failed"]
    blocked_steps = [step for step in steps if step.get("status") == "blocked"]
    open_steps = [step for step in steps if step.get("status") in {"pending", "in_progress"}]
    checks.append(
        {
            "id": "plan_steps",
            "status": "failed" if failed_steps else ("warning" if blocked_steps or open_steps else "passed"),
            "detail": {
                "failed": [step.get("id") for step in failed_steps],
                "blocked": [step.get("id") for step in blocked_steps],
                "open": [step.get("id") for step in open_steps],
            },
        }
    )
    if failed_steps:
        missing.append("failed_steps_resolved")

    constraints = frame.get("constraints") or {}
    if constraints.get("requires_external_facts"):
        has_retrieval = _has_artifact(artifacts, tool_name="web_search") or _has_tool_message(messages or [], "web_search")
        checks.append(
            {
                "id": "external_facts",
                "status": "passed" if has_retrieval else "failed",
                "detail": "web_search result available" if has_retrieval else "missing web_search result for realtime task",
            }
        )
        if not has_retrieval:
            missing.append("web_search_result")

    if constraints.get("requires_governance"):
        has_governance_trace = _has_artifact(artifacts, tool_prefix="ontology_") or _has_runtime_signal(messages or [], "ontology")
        checks.append(
            {
                "id": "governance_trace",
                "status": "passed" if has_governance_trace else "warning",
                "detail": "ontology/runtime trace available" if has_governance_trace else "no ontology runtime trace was attached",
            }
        )

    statuses = [check["status"] for check in checks]
    if "failed" in statuses:
        verdict = "failed"
    elif "warning" in statuses:
        verdict = "warning"
    else:
        verdict = "passed"

    return {
        "status": verdict,
        "checks": checks,
        "missing_requirements": missing,
        "acceptance": frame.get("acceptance") or [],
    }


def _default_acceptance(kind: str) -> list[str]:
    if kind == "realtime_research":
        return ["包含可核查来源", "说明信息时间点", "区分事实、推断和不确定项"]
    if kind == "business_review":
        return ["列出识别字段", "列出命中风险和证据", "说明缺失信息和建议动作"]
    if kind == "engineering":
        return ["说明改动文件", "说明验证命令和结果", "不扩大无关改动范围"]
    return ["直接回答用户目标", "说明关键依据", "标注无法确认的边界"]


def _risk_flags(query: str, kind: str, policy: dict[str, Any]) -> list[str]:
    flags = []
    if kind == "realtime_research" and policy.get("allow_web_search") is False:
        flags.append("task_needs_current_facts_but_web_search_disabled")
    if kind == "engineering" and re.search(r"\b(delete|drop|reset|rm\s+-rf)\b", query or "", re.I):
        flags.append("possible_destructive_operation")
    if kind == "business_review":
        flags.append("business_decision_requires_evidence")
    return flags


def _step(
    step_id: str,
    title: str,
    owner: str,
    tool_candidates: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "title": title,
        "owner": owner,
        "status": "pending",
        "tool_candidates": tool_candidates or [],
        "depends_on": [],
    }


def _resolve_step_id(
    steps: list[dict[str, Any]],
    event_type: str,
    payload: dict[str, Any],
    current_step_id: str | None,
) -> str | None:
    if event_type.startswith("tool_"):
        tool_name = payload.get("tool_name")
        for step in steps:
            if tool_name and tool_name in (step.get("tool_candidates") or []):
                return step.get("id")
        for step in steps:
            if step.get("owner") == "tool" and step.get("status") not in {"completed", "failed", "blocked"}:
                return step.get("id")
    if event_type.startswith("handoff_") or event_type.startswith("orchestrator_invoke_"):
        for step in steps:
            if step.get("owner") == "expert" and step.get("status") not in {"completed", "failed", "blocked"}:
                return step.get("id")
    if event_type == "synthesize_complete":
        for step in steps:
            if step.get("owner") == "expert" and step.get("status") not in {"completed", "failed", "blocked"}:
                return step.get("id")
    return current_step_id or (steps[0].get("id") if steps else None)


def _status_for_event(event_type: str) -> str | None:
    if event_type in {"agent_start", "tool_start", "handoff_start", "orchestrator_invoke_start"}:
        return "in_progress"
    if event_type in {"agent_complete", "tool_success", "handoff_success", "orchestrator_invoke_success", "synthesize_complete"}:
        return "completed"
    if event_type in {"tool_blocked", "handoff_skipped", "orchestrator_invoke_rejected"}:
        return "blocked"
    if event_type in {"tool_error", "handoff_error", "orchestrator_invoke_error", "agent_error"}:
        return "failed"
    return None


def _next_open_step(steps: list[dict[str, Any]], *, start_index: int) -> dict[str, Any] | None:
    terminal = {"completed", "failed", "blocked"}
    for step in steps[start_index + 1:]:
        if step.get("status") not in terminal:
            if step.get("status") == "pending":
                step["status"] = "in_progress"
            return step
    return None


def _event_summary(payload: dict[str, Any]) -> dict[str, Any]:
    keys = ("tool_name", "agent_id", "status", "error", "tool_call_id")
    return {key: payload.get(key) for key in keys if payload.get(key) is not None}


def _has_artifact(
    artifacts: list[dict[str, Any]],
    *,
    tool_name: str | None = None,
    tool_prefix: str | None = None,
) -> bool:
    for artifact in artifacts:
        if artifact.get("status") not in {None, "success", "completed"}:
            continue
        name = artifact.get("tool_name") or ""
        if tool_name and name == tool_name:
            return True
        if tool_prefix and name.startswith(tool_prefix):
            return True
    return False


def _has_tool_message(messages: list[dict[str, Any]], tool_name: str) -> bool:
    return any(msg.get("role") == "tool" and msg.get("name") == tool_name for msg in messages or [])


def _has_runtime_signal(messages: list[dict[str, Any]], signal_name: str) -> bool:
    needle = signal_name.lower()
    for msg in messages or []:
        if needle in str(msg.get("name") or "").lower():
            return True
        if needle in str(msg.get("content") or "").lower():
            return True
    return False


def _compact_text(text: str, max_chars: int) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars] + "..."
