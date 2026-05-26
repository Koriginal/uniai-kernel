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


def _compact_text(text: str, max_chars: int) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars] + "..."
