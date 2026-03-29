"""
用户初始化服务

新用户首次使用时自动分配免费试用模型。
"""
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.provider import ProviderTemplate, UserProvider, UserModelConfig
from app.services.user_provider_manager import user_provider_manager
import logging

logger = logging.getLogger(__name__)

async def init_new_user(session: AsyncSession, user_id: str) -> dict:
    """
    初始化新用户，自动分配免费模型。
    
    Args:
        session: 数据库会话
        user_id: 用户 ID
    
    Returns:
        初始化结果
    """
    # 1. 检查用户是否已初始化
    result = await session.execute(
        select(UserProvider).where(UserProvider.user_id == user_id)
    )
    existing = result.scalars().first()
    if existing:
        logger.info(f"User {user_id} already initialized")
        return {"status": "already_initialized"}
    
    # 2. 查找免费供应商（DeepSeek 或 Groq）
    result = await session.execute(
        select(ProviderTemplate)
        .where(ProviderTemplate.is_free == True)
        .where(ProviderTemplate.is_active == True)
        .limit(1)
    )
    free_template = result.scalar_one_or_none()
    
    if not free_template:
        logger.warning("No free provider template found")
        return {"status": "no_free_provider"}
    
    # 3. 为用户创建免费供应商配置（不需要 API Key）
    user_provider = UserProvider(
        user_id=user_id,
        template_id=free_template.id,
        api_key_encrypted=None,  # 免费模型不需要用户提供 Key
        is_active=True
    )
    session.add(user_provider)
    await session.flush()
    
    # 4. 设置默认 LLM 模型
    if free_template.supported_models:
        default_llm = free_template.supported_models[0]
        llm_config = UserModelConfig(
            user_id=user_id,
            model_type="llm",
            default_model_name=default_llm,
            provider_id=user_provider.id
        )
        session.add(llm_config)
    
    await session.commit()
    
    logger.info(f"Initialized user {user_id} with free provider {free_template.name}")
    
    return {
        "status": "initialized",
        "provider": free_template.name,
        "default_model": free_template.supported_models[0] if free_template.supported_models else None
    }
