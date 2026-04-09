from typing import Annotated, TypedDict, List
from langgraph.graph import StateGraph, END
from app.core.llm import completion
from app.core.config import settings
from app.core.plugins import registry
import logging
import json

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    input: str
    messages: List[dict]
    final_answer: str
    enabled_tools: List[str]  # 运行时允许的能力列表

async def agent_node(state: AgentState):
    """大模型思考与工具调用路由节点"""
    messages = state.get("messages", [])
    if not messages:
        messages = [{"role": "user", "content": state["input"]}]
    
    # 动态获取当前 Agent 允许的 Tools
    enabled_tool_names = state.get("enabled_tools", [])
    all_tools = registry.get_all_actions()
    
    # 根据配置过滤装载
    active_tools = [t for t in all_tools if not enabled_tool_names or t.metadata.name in enabled_tool_names]
    openai_tools = [t.to_openai_format() for t in active_tools] if active_tools else None
    
    response = await completion(
        model=settings.DEFAULT_CHAT_MODEL,
        messages=messages,
        tools=openai_tools
    )
    
    msg = response.choices[0].message
    messages.append(msg.model_dump(exclude_none=True))
    
    return {"messages": messages}

async def tool_node(state: AgentState):
    """工具执行引擎节点"""
    messages = state.get("messages", [])
    last_message = messages[-1]
    
    if "tool_calls" not in last_message or not last_message["tool_calls"]:
        return {"messages": messages}
        
    for tool_call in last_message["tool_calls"]:
        func_name = tool_call["function"]["name"]
        raw_args = tool_call["function"].get("arguments") or "{}"
        
        logger.info(f"[Graph] Executing tool: {func_name} with args: {raw_args}")
        
        try:
            func_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            if not isinstance(func_args, dict):
                raise ValueError("Tool arguments must be a JSON object")
            result = await registry.execute_action(func_name, **func_args)
        except Exception as e:
            result = f"Tool Error: {e}"
            
        messages.append({
            "role": "tool",
            "name": func_name,
            "content": str(result),
            "tool_call_id": tool_call["id"]
        })
        
    return {"messages": messages}

def router(state: AgentState):
    """决定下一步是执行工具还是结束"""
    messages = state.get("messages", [])
    last_message = messages[-1]
    if "tool_calls" in last_message and last_message["tool_calls"]:
        return "tools"
    return "end"

def build_dynamic_agent():
    """
    代理工厂：返回一个组装好的编译状态图。
    基于 LangGraph 的 Tool-Calling (ReAct) 范式抽象。
    """
    workflow = StateGraph(AgentState)
    
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    
    workflow.set_entry_point("agent")
    
    workflow.add_conditional_edges(
        "agent",
        router,
        {
            "tools": "tools",
            "end": END
        }
    )
    
    workflow.add_edge("tools", "agent")  # 执行完工具扔回给 Agent 评估
    
    return workflow.compile()
