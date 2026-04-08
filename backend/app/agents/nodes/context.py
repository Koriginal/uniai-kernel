"""
图节点：上下文构建

对应原 agent_service.py L88-128 的上下文构建逻辑。
负责注入系统提示词、加载记忆、构建完整的 LLM 消息列表。
"""
import json
import logging
from langgraph.types import RunnableConfig
from app.core.graph_state import AgentGraphState
from app.services.context_service import context_service
from app.core.llm import _clean_messages
from app.models.message import ChatMessage
from app.models.session import ChatSession

logger = logging.getLogger(__name__)


async def context_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """
    构建上下文消息（System Prompt + 记忆 + 历史）。

    这是图的入口节点，只执行一次。
    """
    c = config["configurable"]
    callback = c["stream_callback"]
    db = c["db"]
    session_id = c["session_id"]
    user_id = c["user_id"]
    enable_memory = c.get("enable_memory", False)

    messages = list(state["messages"])
    current_agent_id = state["current_agent_id"]
    agent_profile = state["current_agent_profile"]

    # 提取当前用户查询
    current_query = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, list):
                current_query = next((item.get("text", "") for item in content if item.get("type") == "text"), "")
            else:
                current_query = str(content)
            break

    # 会话恢复 / 上下文构建
    if session_id:
        can_resume = False
        session = await db.get(ChatSession, session_id)
        if session:
            if session.active_agent_id != current_agent_id:
                session.active_agent_id = current_agent_id
                db.add(session)
                await db.commit()
            if session.thread_state and "messages" in session.thread_state:
                if session.thread_state.get("agent_id") == current_agent_id:
                    can_resume = True

        if can_resume:
            messages_raw = session.thread_state.get("messages", [])
            messages = _clean_messages(messages_raw)
            messages.append({"role": "user", "content": current_query})
        else:
            # 保存初始 checkpoint
            await _save_checkpoint(db, session_id, messages, status="running", metadata={"agent_id": current_agent_id})
            messages = await context_service.build_context_messages(
                session_id=session_id, user_id=user_id, current_query=current_query,
                db_session=db, max_tokens=4096, enable_memory=enable_memory
            )

        # 保存用户消息到数据库 & 同步 ID 到前端
        if not c.get("skip_save_user", False):
            user_msg = ChatMessage(session_id=session_id, role="user", content=current_query)
            db.add(user_msg)
            await db.commit()
            await callback.emit(f"data: {json.dumps({'type': 'metadata', 'user_message_id': user_msg.id})}\n\n")

    # 创建初始助手消息气泡
    current_msg_id = None
    if session_id:
        initial_msg_db = ChatMessage(session_id=session_id, role="assistant", content="", agent_id=current_agent_id)
        db.add(initial_msg_db)
        await db.commit()
        current_msg_id = initial_msg_db.id
        await callback.emit(f"data: {json.dumps({'type': 'metadata', 'assistant_message_id': current_msg_id, 'agentName': agent_profile.get('name', 'Assistant') if agent_profile else 'Assistant'})}\n\n")

    return {
        "messages": messages,
        "current_msg_id": current_msg_id,
    }


async def _save_checkpoint(db, session_id, messages, status="active", metadata=None):
    """内部辅助：保存会话状态快照"""
    import asyncio
    if not session_id or not db:
        return
    try:
        session = await db.get(ChatSession, session_id)
        if session:
            state_data = {"messages": messages}
            if metadata:
                state_data.update(metadata)
            elif session.thread_state:
                if "agent_id" in session.thread_state:
                    state_data["agent_id"] = session.thread_state["agent_id"]
            session.thread_state = state_data
            session.status = status
            db.add(session)
            await db.commit()
    except Exception as e:
        logger.error(f"[ContextNode] Checkpoint save failed: {e}")
