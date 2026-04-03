from typing import Annotated, TypedDict, List
from langgraph.graph import StateGraph, END
from app.core.llm import completion
from app.core.config import settings

class AgentState(TypedDict):
    input: str
    messages: List[dict]
    final_answer: str

async def reason_node(state: AgentState):
    """
    A simple reasoning node that uses the LLM to process input.
    """
    messages = state.get("messages", [])
    if not messages:
        messages = [{"role": "user", "content": state["input"]}]
    
    # Call LiteLLM
    response = await completion(
        model=settings.DEFAULT_CHAT_MODEL,
        messages=messages
    )
    
    content = response.choices[0].message.content
    return {"messages": messages + [{"role": "assistant", "content": content}], "final_answer": content}

def create_sample_agent():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("reason", reason_node)
    
    workflow.set_entry_point("reason")
    workflow.add_edge("reason", END)
    
    return workflow.compile()
