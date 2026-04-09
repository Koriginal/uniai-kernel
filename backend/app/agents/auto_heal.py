import logging
from typing import Dict, Any, Optional
from app.core.graph_state import AgentGraphState

logger = logging.getLogger(__name__)

class AutoHealManager:
    """
    自愈管理器：图执行中的异常恢复与干预逻辑。
    """
    
    @staticmethod
    async def pre_node_check(state: AgentGraphState, node_name: str) -> Dict[str, Any]:
        """
        节点执行前的自查。
        返回要更新的状态增量。
        """
        trace = state.get("execution_trace", [])
        new_trace = trace + [node_name]
        
        # 记录执行痕迹
        return {
            "execution_trace": new_trace,
        }

    @staticmethod
    async def post_node_success(state: AgentGraphState, node_name: str) -> Dict[str, Any]:
        """
        节点执行成功后的登记。
        """
        return {
            "last_healthy_node": node_name,
            # 成功后可以重置局部重试计数（如果后续引入的话）
        }

    @staticmethod
    async def handle_error(state: AgentGraphState, node_name: str, error: Exception) -> Dict[str, Any]:
        """
        节点执行失败时的干预。
        """
        recovery_count = state.get("recovery_count", 0) + 1
        logger.warning(f"[AutoHeal] Node {node_name} failed (Recovery #{recovery_count}): {error}")
        
        # 简单策略：记录恢复次数
        return {
            "recovery_count": recovery_count,
        }

# 全局单例
auto_heal = AutoHealManager()
