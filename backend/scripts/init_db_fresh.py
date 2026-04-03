import sys, os; sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
import sys
from pathlib import Path

# 将项目根目录加入 python path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import engine, Base
# 导入所有 Model 以确保它们被注册到 Base.metadata
from app.models import (
    ProviderTemplate, UserProvider, UserModelConfig,
    ChatSession, ChatMessage, UserMemory,
    AgentProfile, ActionLog,
    User, UserApiKey
)

async def init_db():
    print("正在初始化数据库表结构...")
    async with engine.begin() as conn:
        # 如果需要彻底重置，可以取消下面这一行的注释
        # await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("✅ 数据库初始化完成！")

if __name__ == "__main__":
    asyncio.run(init_db())
