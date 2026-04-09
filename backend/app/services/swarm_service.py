from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.models.agent import AgentProfile
from app.models.session import ChatSession
from app.core.plugins import registry
from app.agents.agent_scorecard import scorecard

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

        if not target_profile.is_active:
            logger.warning(f"[Swarm] Handoff rejected: Target agent {target_agent_id} is inactive.")
            return None

        if target_profile.role != "expert":
            logger.warning(
                f"[Swarm] Handoff rejected: Target agent {target_agent_id} has role='{target_profile.role}', "
                "but transfer_to_agent only supports expert targets."
            )
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
            AgentProfile.role == "expert",
            AgentProfile.id != current_agent_id
        )
        result = await db.execute(stmt)
        profiles = result.scalars().all()
        expert_ids = [p.id for p in profiles]
        
        # --- [New: Phase 3] 接入评分卡进行排名 ---
        ranked_scores = await scorecard.rank_experts_for_task(db, "general", expert_ids)
        # 将 profile 对象按排名顺序重新整理
        profile_map = {p.id: p for p in profiles}
        ranked_profiles = [profile_map[s.agent_id] for s in ranked_scores if s.agent_id in profile_map]
        
        prompt = "### 🤝 专家协作名录 (EXPERT_DIRECTORY)\n"
        prompt += "当且仅当用户请求涉及以下专业领域且你无法独自高质量回复时，方可调用 `transfer_to_agent`：\n"
        
        if ranked_profiles:
            for p in ranked_profiles:
                # 寻找对应的评分数据
                s = next((score for score in ranked_scores if score.agent_id == p.id), None)
                score_str = f" [成功率: {s.success_rate*100:.0f}%, 质量: {s.avg_quality_score:.1f}]" if s else ""
                prompt += f"- Expert_ID: `{p.id}`, 名称: **{p.name}**{score_str}, 职责: {p.description or '专业领域协助'}\n"
            
            prompt += "\n**协作准则 (CRITICAL RULES)**：\n"
            prompt += "1. 优先调用上方排位靠前、评分较高的专家。\n"
            prompt += "2. 你是对话的唯一主体。专家仅为你提供推演内容。你必须审阅并在协作气泡结束后给出最终 MD 格式回复。\n"
            prompt += "3. **严控 ID 匹配**：仅允许使用上方列表中的 Expert_ID 字符串。**严禁** 将 UI 文本、专家名称（如 'Swarm 专家协同建议'）作为移交目标。\n"
        else:
            prompt += "\n目前暂无其他在线专家。请根据自身知识库独立回复。"
            
        return prompt

    async def get_orchestrator_directory(self, db: AsyncSession, user_id: str, current_agent_id: str) -> str:
        """
        获取可被当前主控委托的子应用（其他主控）目录。
        """
        from sqlalchemy import or_
        stmt = select(AgentProfile).where(
            or_(AgentProfile.user_id == user_id, AgentProfile.is_public == True),
            AgentProfile.is_active == True,
            AgentProfile.role == "orchestrator",
            AgentProfile.id != current_agent_id
        )
        result = await db.execute(stmt)
        profiles = result.scalars().all()

        prompt = "### 🧩 子应用目录 (ORCHESTRATOR_DIRECTORY)\n"
        prompt += "当用户请求更适合交给另一个主控应用整体处理时，可调用 `invoke_orchestrator` 委托子编排。\n"

        if profiles:
            for profile in profiles:
                prompt += f"- App_ID: `{profile.id}`, 名称: **{profile.name}**, 适用范围: {profile.description or '独立编排应用'}\n"
            prompt += "\n**委托准则**：\n"
            prompt += "1. 仅当目标主控在职责边界上明显更合适时再委托。\n"
            prompt += "2. 子主控返回的是子任务结果，你仍需在主控侧完成最终整合。\n"
            prompt += "3. 仅允许使用目录中的 App_ID，严禁凭名称猜测。\n"
        else:
            prompt += "\n当前没有其他可委托的在线主控应用。"

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

    def get_orchestrator_tool_definition(self) -> Dict[str, Any]:
        """
        返回内置的 invoke_orchestrator 工具定义（OpenAI 格式）。
        """
        return {
            "type": "function",
            "function": {
                "name": "invoke_orchestrator",
                "description": "将当前子任务委托给另一个主控应用处理，并在其完成后回收结果继续整合。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "目标主控应用的唯一 ID，必须从 ORCHESTRATOR_DIRECTORY 中精确选择"
                        },
                        "task": {
                            "type": "string",
                            "description": "委托给子主控的明确任务说明"
                        },
                    },
                    "required": ["agent_id"]
                }
            }
        }

swarm_service = SwarmService()
