from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.models.agent import AgentProfile
from app.models.session import ChatSession
from app.core.plugins import registry

logger = logging.getLogger(__name__)

class SwarmService:
    """
    Swarm 多智能体编排服务
    负责处理 Handoff (控制权移交) 逻辑与 Agent 路由。
    """

    async def get_active_agent_profile(self, db: AsyncSession, session_id: str, default_agent_id: str) -> AgentProfile:
        """
        获取当前会话中活跃的智能体 Profile。
        """
        if not session_id or not db:
            return await db.get(AgentProfile, default_agent_id)

        session = await db.get(ChatSession, session_id)
        active_id = session.active_agent_id if session and session.active_agent_id else default_agent_id
        
        profile = await db.get(AgentProfile, active_id)
        if not profile:
            profile = await db.get(AgentProfile, default_agent_id)
        
        return profile

    async def handle_handoff(self, db: AsyncSession, session_id: Optional[str], target_agent_id: str) -> Optional[AgentProfile]:
        """
        执行 Handoff：切换会话的 active_agent_id 并返回新 Profile。
        即使没有 session_id，也准许内存级切换以完成当前请求。
        """
        if not db:
            return None

        # 检查目标 Agent 是否有效
        target_profile = await db.get(AgentProfile, target_agent_id)
        if not target_profile:
            logger.error(f"[Swarm] Handoff failed: Target agent {target_agent_id} not found.")
            return None

        if session_id:
            session = await db.get(ChatSession, session_id)
            if session:
                logger.info(f"[Swarm] Handoff SUCCESS: session {session_id} -> {target_agent_id} (Memory only, preserving session owner)")
        else:
            logger.warning(f"[Swarm] Handoff partial: No session_id provided, performing in-memory switch.")
            
        return target_profile

    async def get_expert_directory(self, db: AsyncSession, user_id: str, current_agent_id: str) -> str:
        """
        获取所有可用的专家 Agent 列表，用于注入 System Prompt。
        作为多智能体协作的核心索引，不再包含看板或 UI 交互逻辑。
        """
        from sqlalchemy import or_
        stmt = select(AgentProfile).where(
            or_(AgentProfile.user_id == user_id, AgentProfile.is_public == True),
            AgentProfile.is_active == True,
            AgentProfile.id != current_agent_id
        )
        result = await db.execute(stmt)
        profiles = result.scalars().all()
        
        prompt = "### 🤝 专家协作名录 (EXPERT_DIRECTORY)\n"
        prompt += "当且仅当用户请求涉及以下专业领域且你无法独自高质量回复时，方可调用 `transfer_to_agent`：\n"
        
        if profiles:
            for p in profiles:
                prompt += f"- Expert_ID: `{p.id}`, 名称: **{p.name}**, 职责: {p.description or '专业领域协助'}\n"
            prompt += "\n**协作准则 (CRITICAL RULES)**：\n"
            prompt += "1. 你是对话的唯一主体。专家仅为你提供推演内容。你必须审阅并在协作气泡结束后给出最终 MD 格式回复。\n"
            prompt += "2. **严控 ID 匹配**：仅允许使用上方列表中的 Expert_ID 字符串。**严禁** 将 UI 文本、专家名称（如 'Swarm 专家协同建议'）作为移交目标。\n"
        else:
            prompt += "\n目前暂无其他在线专家。请根据自身知识库独立回复。"
            
        return prompt

    def get_handoff_tool_definition(self) -> Dict[str, Any]:
        """
        返回内置的 transfer_to_agent 工具定义（OpenAI 格式）。
        """
        return {
            "type": "function",
            "function": {
                "name": "transfer_to_agent",
                "description": "[系统强制指令] 当用户请求涉及专家名录中的 ID 时，你必须立即调用此工具切换上下文。严禁尝试以任何形式亲自回答或解释，严禁返回非 JSON 文本。这是保障系统稳定运行的唯一准许操作。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "目标专家的唯一 ID (必须从 Expert Directory 中精确匹配)"
                        },
                        "reason": {
                            "type": "string",
                            "description": "移交原因简述。"
                        }
                    },
                    "required": ["agent_id"]
                }
            }
        }

swarm_service = SwarmService()
