import asyncio
import os
import sys

# 确保能导入 app 内容
sys.path.append(os.path.join(os.getcwd(), "backend"))
sys.path.append(os.getcwd())

from app.core.db import SessionLocal
from app.models.agent import AgentProfile
from sqlalchemy import update

async def make_public():
    print("🌍 Making all agents public for global collaboration...")
    async with SessionLocal() as db:
        # 将所有智能体标记为公开且激活
        stmt = update(AgentProfile).values(is_public=True, is_active=True)
        await db.execute(stmt)
        await db.commit()
    print("✨ All agents are now public experts.")

if __name__ == "__main__":
    asyncio.run(make_public())
