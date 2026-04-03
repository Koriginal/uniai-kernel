import asyncio
import os
import sys

# 确保能导入 app 内容
sys.path.append(os.path.join(os.getcwd(), "backend"))
sys.path.append(os.getcwd())

from app.core.db import SessionLocal
from app.models.agent import AgentProfile
from sqlalchemy import select

async def check():
    async with SessionLocal() as db:
        r = await db.execute(select(AgentProfile.id, AgentProfile.user_id, AgentProfile.is_active, AgentProfile.is_public))
        res = r.fetchall()
        print(f"Agents in DB: {res}")

if __name__ == "__main__":
    asyncio.run(check())
