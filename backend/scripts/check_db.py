import sys, os; sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
"""检查数据库中的实际配置"""
import asyncio
from app.core.db import SessionLocal
from app.models.provider import UserProvider, UserModelConfig
from sqlalchemy import select

async def check_db():
    async with SessionLocal() as session:
        # 检查 UserProvider
        result = await session.execute(
            select(UserProvider).where(UserProvider.user_id == "admin")
        )
        providers = result.scalars().all()
        
        print(f"\n=== UserProvider (共 {len(providers)} 个) ===")
        for p in providers:
            print(f"  ID: {p.id}")
            print(f"  Template ID: {p.template_id}")
            print(f"  Active: {p.is_active}")
            print(f"  Has Key: {bool(p.api_key_encrypted)}")
            if p.api_key_encrypted:
                print(f"  Key Preview: {p.api_key_encrypted[:20]}...")
            print()
        
        # 检查 UserModelConfig
        result = await session.execute(
            select(UserModelConfig).where(UserModelConfig.user_id == "admin")
        )
        configs = result.scalars().all()
        
        print(f"=== UserModelConfig (共 {len(configs)} 个) ===")
        for c in configs:
            print(f"  Type: {c.model_type}")
            print(f"  Model: {c.default_model_name}")
            print(f"  Provider ID: {c.provider_id}")
            print()

if __name__ == "__main__":
    asyncio.run(check_db())
