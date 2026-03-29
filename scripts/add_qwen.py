"""添加通义千问供应商模板"""
import asyncio
from app.core.db import SessionLocal
from app.models.provider import ProviderTemplate
from sqlalchemy import select

async def add_qwen():
    async with SessionLocal() as db:
        # 检查是否已存在
        result = await db.execute(
            select(ProviderTemplate).where(ProviderTemplate.name == "通义千问")
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            print("[Add] 通义千问模板已存在")
            return
        
        # 添加模板
        qwen = ProviderTemplate(
            name="通义千问",
            provider_type="openai",
            api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            is_free=True,
            requires_api_key=True,
            supported_models=["qwen-turbo", "qwen-plus", "qwen-max"],
            description="阿里云通义千问，免费试用额度",
            config_schema={"api_key": {"required": True, "description": "通义千问 API Key"}}
        )
        db.add(qwen)
        await db.commit()
        print("[Add] ✅ 成功添加通义千问模板")

if __name__ == "__main__":
    asyncio.run(add_qwen())
