from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.core.graph import create_graph
from app.core.llm import completion
from langgraph.graph import END

router = APIRouter()

from langgraph.checkpoint.memory import MemorySaver
import uuid
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Path, Body

# 全局内存 checkpointer (用于演示，重启后丢失)
# 在生产中，请使用 PostgresSaver 或其他持久化 checkpointer
memory = MemorySaver()

# --- 构建全局 Agent 图实例 ---
# 这样我们可以确保所有端点操作的是同一个图定义
def build_agent():
    workflow = create_graph()
    
    # 定义节点
    async def agent_node(state):
        messages = state['messages']
        # 简单的 LLM 调用
        response = await completion(
            model="gpt-3.5-turbo",
            messages=messages
        )
        content = response.choices[0].message.content
        return {"messages": [{"role": "assistant", "content": content}]}

    workflow.add_node("agent", agent_node)
    workflow.set_entry_point("agent")
    workflow.add_edge("agent", END)
    
    return workflow.compile(checkpointer=memory)

agent_app = build_agent()

class AgentRequest(BaseModel):
    query: str
    thread_id: Optional[str] = None

class StateUpdate(BaseModel):
    messages: Optional[List[Dict[str, Any]]] = None
    context: Optional[Dict[str, Any]] = None

@router.post("/run")
async def run_agent(request: AgentRequest):
    """
    [便利接口] 执行一个通用 agent 流程。
    如果提供了 thread_id，将保持会话状态。
    """
    try:
        # 配置线程 ID
        thread_id = request.thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        
        # 构造输入
        initial_state = {"messages": [{"role": "user", "content": request.query}]}
        
        # 运行图
        result = await agent_app.ainvoke(initial_state, config=config)
        
        last_message = result['messages'][-1]['content']
        return {
            "result": last_message, 
            "trace": result.get("steps", []),
            "thread_id": thread_id
        }

    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- 原始状态机接口 (Raw State Machine API) ---

@router.get("/{thread_id}/state")
async def get_agent_state(thread_id: str):
    """
    获取指定线程的当前状态快照。
    用于查看当前上下文和执行历史。
    """
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = await agent_app.aget_state(config)
    return {
        "values": state_snapshot.values,
        "next": state_snapshot.next,
        "config": state_snapshot.config
    }

@router.post("/{thread_id}/state")
async def update_agent_state(
    thread_id: str, 
    update: StateUpdate
):
    """
    手动更新指定线程的状态（"自己拼上下文"）。
    可以直接注入消息或修改上下文变量，而不触发 LLM 运行。
    """
    config = {"configurable": {"thread_id": thread_id}}
    
    # 构造更新 payload
    state_update = {}
    if update.messages:
        state_update["messages"] = update.messages
    if update.context:
        state_update["context"] = update.context
        
    await agent_app.aupdate_state(config, state_update)
    
    # 返回更新后的状态
    new_snapshot = await agent_app.aget_state(config)
    return {"status": "updated", "current_values": new_snapshot.values}

@router.post("/{thread_id}/run")
async def trigger_agent_run(
    thread_id: str,
    input: Optional[Dict[str, Any]] = Body(None)
):
    """
    手动触发指定线程的状态机运行。
    通常在手动更新状态后调用。
    """
    config = {"configurable": {"thread_id": thread_id}}
    
    # 如果没有输入，传入 None 试图 resume
    inputs = input if input else None
    
    result = await agent_app.ainvoke(inputs, config=config)
    
    # 尝试提取最后一条消息
    last_content = None
    if "messages" in result and result["messages"]:
        last_content = result["messages"][-1].get("content")

    return {
        "status": "completed",
        "result": last_content,
        "full_state": result
    }

import logging
logger = logging.getLogger(__name__)
