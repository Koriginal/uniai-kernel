from fastapi import APIRouter
from app.api.endpoints import llm, agent, providers, sessions, memories, chat, user_init

api_router = APIRouter()
api_router.include_router(llm.router, prefix="/llm", tags=["模型服务"])
api_router.include_router(agent.router, prefix="/agents", tags=["智能体服务"])
api_router.include_router(providers.router, prefix="/providers", tags=["供应商管理"])
api_router.include_router(sessions.router, prefix="/chat-sessions", tags=["会话管理"])
api_router.include_router(memories.router, prefix="/memories", tags=["记忆管理"])
api_router.include_router(chat.router, prefix="/chat", tags=["智能对话"])
api_router.include_router(user_init.router, prefix="/users", tags=["用户管理"])

