from fastapi import APIRouter
from app.api.endpoints import (
    agents, 
    providers, 
    sessions, 
    memories, 
    user_init, 
    completions,
    embeddings,
    audit,
    registry,
    llm,
    api_keys,
    dynamic_tools,
    auth,
    users,
    messages as messages_ep
)

api_router = APIRouter()

# --- 1. [核心分发面] OpenAI 标准兼容协议网关 ---
# 专门留给标准化第三方工具对接，路径必须保持 /v1 开头
api_router.include_router(completions.router, prefix="/v1", tags=["OpenAI Standard Gateway"])
api_router.include_router(embeddings.router, prefix="/v1", tags=["OpenAI Standard Gateway"])

# --- 2. [控制管理面] 内核管理子系统 (API v1) ---
# 供开发者通过 Dashboard 或脚本配置供应商、智能体、记忆等资源
mgmt_router = APIRouter(prefix="/api/v1")

mgmt_router.include_router(agents.router, prefix="/agents", tags=["Agent Profiles"])
mgmt_router.include_router(providers.router, prefix="/providers", tags=["Provider Management"])
mgmt_router.include_router(sessions.router, prefix="/chat-sessions", tags=["Session Tracking"])
mgmt_router.include_router(messages_ep.router, prefix="/messages", tags=["Message Management"])
mgmt_router.include_router(memories.router, prefix="/memories", tags=["Memory & RAG"])
mgmt_router.include_router(audit.router, prefix="/audit", tags=["Audit Traceability"])
mgmt_router.include_router(registry.router, prefix="/registry", tags=["Asset Inventory"])
mgmt_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
mgmt_router.include_router(users.router, prefix="/users", tags=["User Management"])
mgmt_router.include_router(user_init.router, prefix="/user-init", tags=["User Lifecycle"])
mgmt_router.include_router(llm.router, prefix="/llm", tags=["LLM Raw Access"])
mgmt_router.include_router(api_keys.router, prefix="/user/api-keys", tags=["API Keys"])
mgmt_router.include_router(dynamic_tools.router, prefix="/dynamic-tools", tags=["Dynamic Tools"])

# --- 3. [图引擎面] LangGraph 图拓扑与调试 ---
from app.api.endpoints import graph as graph_ep
mgmt_router.include_router(graph_ep.router, prefix="/graph", tags=["Graph Engine"])

api_router.include_router(mgmt_router)
