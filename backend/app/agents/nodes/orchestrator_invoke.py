"""
图节点：子主控调用（Orchestrator Invoke）

负责处理 invoke_orchestrator 调用，将当前执行上下文切换到目标主控应用。
这条链路与专家 handoff 分离，作为应用级编排的独立路径。
"""
import json
import logging
from langgraph.types import RunnableConfig

from app.core.graph_state import AgentGraphState
from app.services.swarm_service import swarm_service
from app.ontology.registry import ontology_registry
from app.ontology.schema import SemanticContext, SemanticFrame, SemanticSlots

logger = logging.getLogger(__name__)


async def orchestrator_invoke_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    c = config["configurable"]
    callback = c["stream_callback"]
    db = c["db"]
    session_id = c["session_id"]

    messages = list(state["messages"])
    pending_tool_calls = state["pending_tool_calls"]
    called_expert_ids = list(state["called_expert_ids"])
    iter_text = state["iter_text"]
    semantic_slots = dict(state.get("semantic_slots") or {})
    semantic_frame = dict(state.get("semantic_frame") or {})
    interaction_mode = state.get("interaction_mode", "chat")
    orchestrator_agent_id = c.get("orchestrator_agent_id")

    invoke_calls = [
        tc for tc in pending_tool_calls
        if tc.get("function", {}).get("name") == "invoke_orchestrator"
    ]

    messages.append({
        "role": "assistant",
        "content": iter_text or None,
        "tool_calls": list(pending_tool_calls)
    })

    new_agent_id = state["current_agent_id"]
    new_agent_profile = state["current_agent_profile"]
    pending_delegate_type = None

    semantic = SemanticContext(
        interaction_mode=interaction_mode,
        frame=SemanticFrame(**semantic_frame) if semantic_frame else SemanticFrame(interaction_mode=interaction_mode),
        slots=SemanticSlots(**semantic_slots) if semantic_slots else SemanticSlots(),
    )

    for tc in invoke_calls:
        try:
            args = json.loads(tc["function"]["arguments"])
            tid = str(args.get("agent_id") or "").strip()
            requested_task = (args.get("task") or "").strip()
            if not tid:
                messages.append({
                    "role": "tool",
                    "name": "invoke_orchestrator",
                    "content": "Rejected: missing target orchestrator id.",
                    "tool_call_id": tc["id"]
                })
                continue

            if tid == new_agent_id:
                messages.append({
                    "role": "tool",
                    "name": "invoke_orchestrator",
                    "content": f"Skipped: application '{tid}' is already active.",
                    "tool_call_id": tc["id"]
                })
                continue

            if tid == orchestrator_agent_id and state["current_agent_id"] != orchestrator_agent_id:
                messages.append({
                    "role": "tool",
                    "name": "invoke_orchestrator",
                    "content": "Skipped: root orchestrator handback is managed by runtime.",
                    "tool_call_id": tc["id"]
                })
                continue

            if tid in called_expert_ids:
                messages.append({
                    "role": "tool",
                    "name": "invoke_orchestrator",
                    "content": f"Skipped: application '{tid}' already consulted.",
                    "tool_call_id": tc["id"]
                })
                continue

            decision = ontology_registry.delegation_policy.evaluate_orchestrator_delegate(
                semantic,
                requested_task=requested_task,
            )
            if not decision.allow_delegate:
                messages.append({
                    "role": "tool",
                    "name": "invoke_orchestrator",
                    "content": f"Rejected by policy: {decision.reason} (confidence={decision.confidence:.2f}).",
                    "tool_call_id": tc["id"]
                })
                continue

            delegated_task = decision.recommended_task or requested_task
            orchestrator = await swarm_service.handle_handoff(db, session_id, tid)
            if orchestrator and orchestrator.role == "orchestrator":
                called_expert_ids.append(tid)
                new_agent_id = orchestrator.id
                new_agent_profile = {
                    "id": orchestrator.id,
                    "name": orchestrator.name,
                    "description": orchestrator.description,
                    "system_prompt": orchestrator.system_prompt,
                    "tools": orchestrator.tools or [],
                    "model_config_id": orchestrator.model_config_id,
                    "role": orchestrator.role,
                    "routing_keywords": orchestrator.routing_keywords,
                    "handoff_strategy": orchestrator.handoff_strategy,
                    "is_public": orchestrator.is_public,
                    "runtime_mode": "delegate_orchestrator",
                }
                interaction_mode = "delegated_app"
                pending_delegate_type = "orchestrator"
                if delegated_task:
                    semantic_slots["delegated_task"] = delegated_task

                await callback.emit(
                    f"data: {json.dumps({'type': 'status', 'state': 'active', 'agentName': orchestrator.name, 'content': '正在启动子应用编排...'})}\n\n"
                )
                messages.append({
                    "role": "tool",
                    "name": "invoke_orchestrator",
                    "content": (
                        f"Successfully invoked sub-orchestrator: {orchestrator.name}. "
                        f"policy={decision.reason}, confidence={decision.confidence:.2f}, "
                        f"task={delegated_task or 'N/A'}"
                    ),
                    "tool_call_id": tc["id"]
                })
            else:
                messages.append({
                    "role": "tool",
                    "name": "invoke_orchestrator",
                    "content": f"Application Error: target orchestrator '{tid}' unavailable.",
                    "tool_call_id": tc["id"]
                })
        except Exception as e:
            logger.error(f"[OrchestratorInvokeNode] Invoke failed: {e}")
            messages.append({
                "role": "tool",
                "name": "invoke_orchestrator",
                "content": f"Application Error: {e}",
                "tool_call_id": tc["id"]
            })

    return {
        "messages": messages,
        "current_agent_id": new_agent_id,
        "current_agent_profile": new_agent_profile,
        "called_expert_ids": called_expert_ids,
        "iter_text": "",
        "pending_tool_calls": [],
        "interaction_mode": interaction_mode,
        "pending_delegate_type": pending_delegate_type,
        "semantic_slots": semantic_slots,
    }
