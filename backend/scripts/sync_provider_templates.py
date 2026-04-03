import sys, os; sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
"""
同步供应商模板数据至数据库 (Upsert 逻辑)
"""
import asyncio
from dotenv import load_dotenv
# 必须在 app.core.config 的 settings 实例化之前加载 .env
# 确定 .env 绝对路径
dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path)

from app.core.db import SessionLocal
from app.models.provider import ProviderTemplate
from app.config.provider_templates import PROVIDER_TEMPLATES
from sqlalchemy import select

async def sync_templates():
    async with SessionLocal() as db:
        print("[Sync] 正在同步供应商模板数据...")
        
        for data in PROVIDER_TEMPLATES:
            # 查找是否已存在同名模板
            result = await db.execute(
                select(ProviderTemplate).where(ProviderTemplate.name == data["name"])
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # 更新已有模板的模型列表和描述
                print(f"  -> 更新库中已有模板: {data['name']}")
                existing.supported_models = data["supported_models"]
                existing.description = data["description"]
                existing.api_base = data["api_base"]
                existing.provider_type = data["provider_type"]
                db.add(existing)
            else:
                # 插入新模板
                print(f"  + 导入新模板预设: {data['name']}")
                new_template = ProviderTemplate(**data)
                db.add(new_template)
        
        await db.commit()
        print(f"[Sync] ✅ 同步完成，共处理 {len(PROVIDER_TEMPLATES)} 个模板")

if __name__ == "__main__":
    asyncio.run(sync_templates())
