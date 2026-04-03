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
                session.active_agent_id = target_agent_id
                db.add(session)
                await db.commit()
                logger.info(f"[Swarm] Handoff SUCCESS: session {session_id} -> {target_agent_id}")
        else:
            logger.warning(f"[Swarm] Handoff partial: No session_id provided, performing in-memory switch.")
            
        return target_profile

    async def get_all_experts_prompt(self, db: AsyncSession, user_id: str, current_agent_id: str) -> str:
        """
        获取所有可用的专家 Agent 列表，用于注入 System Prompt。
        """
        from sqlalchemy import or_
        stmt = select(AgentProfile).where(
            or_(AgentProfile.user_id == user_id, AgentProfile.is_public == True),
            AgentProfile.is_active == True,
            AgentProfile.id != current_agent_id
        )
        result = await db.execute(stmt)
        profiles = result.scalars().all()
        
        if not profiles:
            return ""
            
        prompt = "\n\n### 🛡️ 核心管理指令：协作调度 (ADMIN_COLLABORATION_FORCE)\n"
        prompt += "你当前拥有最高层级的 [协作调度权]。当任务涉及以下专业场景时，你必须保持沉默并直接调用 `transfer_to_agent`，严禁尝试自己回答：\n"
        for p in profiles:
            prompt += f"- ID: `{p.id}`, 名称: **{p.name}**, 职责范围: {p.description or '该专家负责处理其专业领域的深度问题'}\n"
        prompt += "\n**操作规范**：不要尝试展示你的能力，直接触发移交。若你返回文本而非工具调用，将被视为一次严重的系统故障。"
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
