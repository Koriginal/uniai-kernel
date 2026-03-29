"""
初始化系统供应商模板数据

从统一配置文件加载。
"""
import asyncio
from app.core.db import SessionLocal
from app.models.provider import ProviderTemplate
from app.config.provider_templates import PROVIDER_TEMPLATES

async def init_provider_templates():
    """初始化供应商模板数据"""
    async with SessionLocal() as db:
        # 检查是否已初始化
        from sqlalchemy import select
        result = await db.execute(select(ProviderTemplate))
        existing = result.scalars().all()
        
        if existing:
            print(f"[Init] 已有 {len(existing)} 个供应商模板，跳过初始化")
            return
        
        # 批量插入
        for data in PROVIDER_TEMPLATES:
            template = ProviderTemplate(**data)
            db.add(template)
        
        await db.commit()
        print(f"[Init] ✅ 成功初始化 {len(PROVIDER_TEMPLATES)} 个供应商模板")
        for t in PROVIDER_TEMPLATES:
            print(f"  - {t['name']}: {', '.join(t['supported_models'][:2])}")

if __name__ == "__main__":
    asyncio.run(init_provider_templates())
