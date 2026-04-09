import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from langgraph.graph import END

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
            has_handoff = any(
                tc.get("function", {}).get("name") in {"transfer_to_agent", "invoke_orchestrator"}
                for tc in pending
            )
            return "handoff" if has_handoff else "tool_executor"
            
        orchestrator_id = config.get("configurable", {}).get("orchestrator_agent_id", "")
        if state.get("current_agent_id") != orchestrator_id:
            return "synthesize"
            
        return END

class ScoreBasedStrategy(RoutingStrategy):
    """
    基于评分的路由策略：在 Handoff 决策中，提示选择更高分的专家。
    (目前逻辑在 swarm_service 中实现，此处做路由终点路由)。
    """
    async def decide_next(self, state: AgentGraphState, config: Dict[str, Any]) -> str:
        # 该策略目前暂时复用基础逻辑，但在路由跳转决策上可增加健康度分析
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
