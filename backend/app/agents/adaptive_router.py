import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from langgraph.graph import END
import json

from app.core.graph_state import AgentGraphState
from app.agents.agent_scorecard import scorecard

logger = logging.getLogger(__name__)

class RoutingStrategy(ABC):
    """
    路由策略抽象接口。
    """
    @abstractmethod
    async def decide_next(self, state: AgentGraphState, config: Dict[str, Any]) -> str:
        pass

class DeterministicStrategy(RoutingStrategy):
    """
    确定性策略（当前硬编码逻辑的基座）。
    """
    async def decide_next(self, state: AgentGraphState, config: Dict[str, Any]) -> str:
        pending = state.get("pending_tool_calls", [])
        if pending:
            has_orchestrator_invoke = any(
                tc.get("function", {}).get("name") == "invoke_orchestrator"
                for tc in pending
            )
            has_handoff = any(
                tc.get("function", {}).get("name") == "transfer_to_agent"
                for tc in pending
            )
            if has_orchestrator_invoke:
                return "orchestrator_invoke"
            return "handoff" if has_handoff else "tool_executor"
            
        orchestrator_id = config.get("configurable", {}).get("orchestrator_agent_id", "")
        if state.get("current_agent_id") != orchestrator_id:
            return "synthesize"
            
        return END

class ScoreBasedStrategy(RoutingStrategy):
    """
    基于评分的路由策略：在 Handoff 决策中，提示选择更高分的专家。
    若 LLM 一次给出多个 transfer_to_agent 候选，按评分仅保留最佳候选。
    """
    @staticmethod
    def _extract_target_agent_id(tool_call: Dict[str, Any]) -> Optional[str]:
        try:
            if tool_call.get("function", {}).get("name") != "transfer_to_agent":
                return None
            raw_args = tool_call.get("function", {}).get("arguments") or "{}"
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            if isinstance(args, dict):
                target = args.get("agent_id")
                return str(target) if target else None
        except Exception:
            return None
        return None

    @staticmethod
    def _latest_user_intent(state: AgentGraphState) -> str:
        for msg in reversed(state.get("messages", [])):
            if msg.get("role") == "user":
                content = msg.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    texts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
                    return " ".join([t for t in texts if t]).strip()
        return "general"

    async def decide_next(self, state: AgentGraphState, config: Dict[str, Any]) -> str:
        pending = state.get("pending_tool_calls", [])
        transfer_calls = [
            tc for tc in pending
            if tc.get("function", {}).get("name") == "transfer_to_agent"
        ]

        # 仅在出现多个候选专家时触发评分重排
        if len(transfer_calls) > 1:
            db = config.get("configurable", {}).get("db")
            if db:
                candidate_ids = []
                call_by_agent_id: Dict[str, Dict[str, Any]] = {}
                for call in transfer_calls:
                    target_id = self._extract_target_agent_id(call)
                    if not target_id:
                        continue
                    candidate_ids.append(target_id)
                    # 后出现的候选覆盖前者，避免重复 id 带来不确定性
                    call_by_agent_id[target_id] = call

                if candidate_ids:
                    try:
                        ranked = await scorecard.rank_experts_for_task(
                            db=db,
                            task_description=self._latest_user_intent(state),
                            expert_ids=list(dict.fromkeys(candidate_ids))
                        )
                        if ranked:
                            best_id = ranked[0].agent_id
                            best_call = call_by_agent_id.get(best_id)
                            if best_call:
                                # 保留最佳 transfer_to_agent，其余工具调用不变
                                non_transfer_calls = [
                                    tc for tc in pending
                                    if tc.get("function", {}).get("name") != "transfer_to_agent"
                                ]
                                state["pending_tool_calls"] = non_transfer_calls + [best_call]
                                logger.info(
                                    f"[AdaptiveRouter] ScoreBased selected best expert={best_id} "
                                    f"from candidates={list(dict.fromkeys(candidate_ids))}"
                                )
                    except Exception as e:
                        logger.warning(f"[AdaptiveRouter] Score-based ranking failed, fallback deterministic: {e}")

        return await DeterministicStrategy().decide_next(state, config)

class AdaptiveRouter:
    """
    自适应路由器：管理并执行多种路由策略。
    """
    def __init__(self):
        self.strategies: Dict[str, RoutingStrategy] = {
            "deterministic": DeterministicStrategy(),
            "score_based": ScoreBasedStrategy()
        }
        self.current_strategy = "score_based"

    async def route(self, state: AgentGraphState, config: Dict[str, Any]) -> str:
        """
        核心路由入口。
        """
        # 1. 基础防护：最大迭代限制
        max_iter = config.get("configurable", {}).get("max_iterations", 10)
        if state.get("iteration_count", 0) >= max_iter:
            logger.warning(f"[AdaptiveRouter] Max iterations ({max_iter}) reached.")
            return END
            
        # 2. 执行选定策略
        strategy = self.strategies.get(self.current_strategy, self.strategies["deterministic"])
        next_node = await strategy.decide_next(state, config)
        
        logger.debug(f"[AdaptiveRouter] Strategy '{self.current_strategy}' decided next: {next_node}")
        return next_node

# 全局单例
router = AdaptiveRouter()
