import sys, os; sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
"""完全重置 admin（解决加密密钥问题）"""
import asyncio
from app.core.db import SessionLocal
from app.core.config import settings
from app.models.provider import ProviderTemplate, UserProvider, UserModelConfig
from sqlalchemy import select, delete

async def reset_and_reinit():
    """完全清空并重新初始化"""
    async with SessionLocal() as session:
        user_id = "admin"
        
        # 1. 完全删除旧数据
        await session.execute(delete(UserModelConfig).where(UserModelConfig.user_id == user_id))
        await session.execute(delete(UserProvider).where(UserProvider.user_id == user_id))
        await session.commit()
        print(f"[Reset] ✅ 清空所有旧配置")
        
        # 2. 检查环境变量
        if not settings.DEFAULT_LLM_PROVIDER or not settings.DEFAULT_LLM_API_KEY:
            print("[Reset] ❌ 环境变量未配置")
            print(f"  DEFAULT_LLM_PROVIDER: {settings.DEFAULT_LLM_PROVIDER}")
            print(f"  DEFAULT_LLM_MODEL: {settings.DEFAULT_LLM_MODEL}")
            print(f"  DEFAULT_LLM_API_KEY: {'已设置' if settings.DEFAULT_LLM_API_KEY else '未设置'}")
            return
        
        # 3. 查找模板
        result = await session.execute(
            select(ProviderTemplate).where(
                ProviderTemplate.name == settings.DEFAULT_LLM_PROVIDER
            )
        )
        template = result.scalar_one_or_none()
        
        if not template:
            print(f"[Reset] ❌ 模板 '{settings.DEFAULT_LLM_PROVIDER}' 不存在")
            return
        
        # 4. 用新密钥加密并创建
        from app.services.user_provider_manager import user_provider_manager
        
        user_provider = await user_provider_manager.create_user_provider(
            session,
            user_id,
            settings.DEFAULT_LLM_PROVIDER,
            settings.DEFAULT_LLM_API_KEY,
            {}
        )
        
        model_name = settings.DEFAULT_LLM_MODEL or template.supported_models[0]
        await user_provider_manager.set_default_model(
            session, user_id, "llm", model_name, user_provider.id
        )
        
        print(f"[Reset] ✅ 成功重新配置")
        print(f"  Provider: {settings.DEFAULT_LLM_PROVIDER}")
        print(f"  Model: {model_name}")
        print(f"  API Key: 已用新密钥加密")

if __name__ == "__main__":
    asyncio.run(reset_and_reinit())
