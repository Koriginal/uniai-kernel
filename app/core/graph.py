from typing import Annotated, Dict, Any, List, TypedDict, Union
from langgraph.graph import StateGraph, END
import operator

# 通用 agent 的基本状态定义
class AgentState(TypedDict):
    messages: List[Dict[str, Any]]
    context: Dict[str, Any]
    steps: List[str]

# 创建基本图的辅助函数
def create_graph():
    return StateGraph(AgentState)

# 为方便起见，重新导出关键的 LangGraph 组件
__all__ = ["StateGraph", "END", "AgentState", "create_graph"]
