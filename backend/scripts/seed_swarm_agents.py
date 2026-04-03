import sys, os; sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
import logging
from app.core.db import SessionLocal
from app.models.agent import AgentProfile
from app.models.provider import UserModelConfig
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)

async def seed_swarm_agents():
    async with SessionLocal() as db:
        # 获取默认模型配置
        res = await db.execute(select(UserModelConfig).limit(1))
        default_config = res.scalar_one_or_none()
        
        if not default_config:
            logging.error("No default model config found. Please run auto-config first.")
            return

        experts = [
            {
                "id": "agent-orchestrator",
                "name": "UniAI 总控助手",
                "description": "擅长任务拆解与分发，能识别用户意图并调度合适的专家。",
                "system_prompt": "你是一个总控调度员。当用户提出特定领域的复杂任务时，请调用 transfer_to_agent 工具将任务移交给对应的专家：\n- 写代码 -> agent-coder\n- 翻译 -> agent-translator\n- 查资料 -> agent-searcher",
                "tools": ["*"]
            },
            {
                "id": "agent-coder",
                "name": "代码专家",
                "description": "专注于 Python, JS, C++ 等主流语言的开发与重构。",
                "system_prompt": "你是一个极简主义的顶级程序员。你只提供高内聚、低耦合的代码实现。如果任务涉及非代码领域（如翻译），请移交给 agent-translator。",
                "tools": ["*"]
            },
            {
                "id": "agent-searcher",
                "name": "搜索专家",
                "description": "擅长深度搜索与信息提炼。",
                "system_prompt": "你是一个严谨的信息分析师。请优先使用 web_search 工具获取最新资讯。如果是技术开发问题，请移交给 agent-coder。",
                "tools": ["web_search", "transfer_to_agent"]
            }
        ]

        for exp in experts:
            # 检查是否已存在
            res = await db.execute(select(AgentProfile).where(AgentProfile.id == exp["id"]))
            if res.scalar_one_or_none():
                logging.info(f"Agent {exp['id']} already exists, skipping.")
                continue
                
            agent = AgentProfile(
                id=exp["id"],
                name=exp["name"],
                description=exp["description"],
                system_prompt=exp["system_prompt"],
                model_config_id=default_config.id,
                tools=exp["tools"],
                is_public=True,
                user_id="system"
            )
            db.add(agent)
            logging.info(f"Seeded agent: {exp['id']}")

        await db.commit()

if __name__ == "__main__":
    asyncio.run(seed_swarm_agents())
