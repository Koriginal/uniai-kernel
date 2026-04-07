import sys, os; sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
"""重新初始化 admin（从环境变量）"""
import asyncio
from app.core.db import SessionLocal
from app.core.config import settings
from app.models.provider import ProviderTemplate, UserProvider, UserModelConfig
from app.services.user_provider_manager import user_provider_manager
from sqlalchemy import select, delete

async def reinit_admin():
    """删除旧配置，从环境变量重新初始化"""
    async with SessionLocal() as session:
        user_id = "admin"
        
        # 1. 删除旧配置
        await session.execute(delete(UserModelConfig).where(UserModelConfig.user_id == user_id))
        await session.execute(delete(UserProvider).where(UserProvider.user_id == user_id))
        await session.commit()
        print(f"[Reinit] 清除旧配置")
        
        # 2. 检查环境变量
        if not settings.DEFAULT_LLM_PROVIDER:
            print("[Reinit] ❌ DEFAULT_LLM_PROVIDER 未设置")
            return
        
        print(f"[Reinit] 读取环境变量:")
        print(f"  Provider: {settings.DEFAULT_LLM_PROVIDER}")
        print(f"  Model: {settings.DEFAULT_LLM_MODEL}")
        print(f"  API Key: {'已设置' if settings.DEFAULT_LLM_API_KEY else '未设置'}")
        
        # 3. 查找模板
        result = await session.execute(
            select(ProviderTemplate).where(
                ProviderTemplate.name == settings.DEFAULT_LLM_PROVIDER
            )
        )
        template = result.scalar_one_or_none()
        
        if not template:
            print(f"[Reinit] ❌ 模板 '{settings.DEFAULT_LLM_PROVIDER}' 不存在")
            return
        
        # 4. 创建用户供应商
        user_provider = await user_provider_manager.create_user_provider(
            session,
            user_id,
            settings.DEFAULT_LLM_PROVIDER,
            settings.DEFAULT_LLM_API_KEY,
            {}
        )
        
        # 5. 设置默认 LLM
        model_name = settings.DEFAULT_LLM_MODEL or template.supported_models[0]
        await user_provider_manager.set_default_model(
            session, user_id, "llm", model_name, user_provider.id
        )
        
        print(f"[Reinit] ✅ 成功配置 {settings.DEFAULT_LLM_PROVIDER} / {model_name}")

if __name__ == "__main__":
    asyncio.run(reinit_admin())
