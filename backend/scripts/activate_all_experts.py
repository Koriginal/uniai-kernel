import asyncio
import os
import sys

# 确保能导入 app 内容
sys.path.append(os.path.join(os.getcwd(), "backend"))
sys.path.append(os.getcwd())

from app.core.db import SessionLocal
from app.models.agent import AgentProfile
from sqlalchemy import select, update

async def activate_experts():
    print("🚀 Activating all expert agents in database...")
    async with SessionLocal() as db:
        # 1. 激活所有非总控的智能体
        stmt = update(AgentProfile).where(AgentProfile.id != "agent-orchestrator").values(is_active=True)
        await db.execute(stmt)
        
        # 2. 检查当前有哪些专家
        result = await db.execute(select(AgentProfile).where(AgentProfile.is_active == True))
        agents = result.scalars().all()
        print(f"✅ Currently Active Agents: {[a.id for a in agents]}")
        
        await db.commit()
    print("✨ Activation finished.")

if __name__ == "__main__":
    asyncio.run(activate_experts())
