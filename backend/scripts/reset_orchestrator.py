import asyncio
import os
import sys

# 确保能导入 app 内容
sys.path.append(os.path.join(os.getcwd(), "backend"))
sys.path.append(os.getcwd())

from app.core.db import SessionLocal
from app.models.agent import AgentProfile
from sqlalchemy import select, update

async def reset_orchestrator():
    print("🔄 Resetting agent-orchestrator system prompt...")
    standard_prompt = "你是一个总控调度员。当用户提出特定领域的复杂任务时，请优先调用 transfer_to_agent 工具将任务移交给对应的专家。当前的对话历史和记忆已经整合，请根据以下指令和专家名录进行调度。"
    
    async with SessionLocal() as db:
        stmt = update(AgentProfile).where(AgentProfile.id == "agent-orchestrator").values(system_prompt=standard_prompt)
        await db.execute(stmt)
        await db.commit()
    print("✅ Orchestrator prompt reset finished.")

if __name__ == "__main__":
    asyncio.run(reset_orchestrator())
