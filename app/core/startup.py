"""
启动时自动配置

从环境变量读取默认模型配置，自动为 default_user 初始化。
"""
import asyncio
from app.core.config import settings
from app.core.db import SessionLocal
from app.models.provider import ProviderTemplate, UserProvider, UserModelConfig
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)

async def auto_configure_default_user():
    """
    启动时自动配置默认用户的模型。
    
    从环境变量读取配置：
    - DEFAULT_LLM_PROVIDER: 供应商名称
    - DEFAULT_LLM_MODEL: 模型名称
    - DEFAULT_LLM_API_KEY: API Key
    """
    if not settings.DEFAULT_LLM_PROVIDER:
        logger.info("[Auto-Config] No DEFAULT_LLM_PROVIDER set, skipping auto-config")
        return
    
    async with SessionLocal() as session:
        user_id = "default_user"
        
        # 1. 检查是否已配置
        result = await session.execute(
            select(UserProvider).where(UserProvider.user_id == user_id)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            logger.info(f"[Auto-Config] default_user already configured")
            return
        
        # 2. 查找模板
        result = await session.execute(
            select(ProviderTemplate).where(
                ProviderTemplate.name == settings.DEFAULT_LLM_PROVIDER
            )
        )
        template = result.scalar_one_or_none()
        
        if not template:
            logger.warning(f"[Auto-Config] Template '{settings.DEFAULT_LLM_PROVIDER}' not found")
            return
        
        # 3. 创建用户供应商
        from app.services.user_provider_manager import user_provider_manager
        
        try:
            user_provider = await user_provider_manager.create_user_provider(
                session,
                user_id,
                settings.DEFAULT_LLM_PROVIDER,
                settings.DEFAULT_LLM_API_KEY,
                {}
            )
            
            # 4. 设置默认模型（支持多种类型）
            model_configs = [
                ("llm", settings.DEFAULT_LLM_MODEL),
                ("embedding", settings.DEFAULT_EMBEDDING_MODEL),
                ("rerank", settings.DEFAULT_RERANK_MODEL),
                ("tts", settings.DEFAULT_TTS_MODEL),
                ("stt", settings.DEFAULT_STT_MODEL),
            ]
            
            configured = []
            for model_type, model_name in model_configs:
                if not model_name and model_type == "llm":
                    # LLM 使用模板默认
                    model_name = template.supported_models[0] if template.supported_models else None
                
                if model_name:
                    await user_provider_manager.set_default_model(
                        session, user_id, model_type, model_name, user_provider.id
                    )
                    configured.append(f"{model_type}={model_name}")
            
            logger.info(f"[Auto-Config] ✅ Configured default_user: {', '.join(configured)}")
            
        except Exception as e:
            logger.error(f"[Auto-Config] Failed: {e}")

if __name__ == "__main__":
    asyncio.run(auto_configure_default_user())
