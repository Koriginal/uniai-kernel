from typing import Any, Dict, List, Optional, Union
import litellm
from app.core.config import settings
from app.core.db import SessionLocal
from app.models.provider import UserProvider, UserModelConfig, ProviderTemplate
from app.services.user_provider_manager import user_provider_manager
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)

# 配置 LiteLLM 全局回退（如果有）
if hasattr(settings, 'OPENAI_API_KEY') and settings.OPENAI_API_KEY:
    litellm.api_key = settings.OPENAI_API_KEY

async def get_user_model_config(
    user_id: str,
    model_type: str = "llm"
) -> tuple[str, str, str, dict, str] | None:
    """
    获取用户的模型配置（多租户版本）。
    
    Returns:
        (model_name, api_key, api_base, extra_config, provider_type) 或 None
    """
    async with SessionLocal() as session:
        # 1. 查找用户默认模型配置
        result = await session.execute(
            select(UserModelConfig)
            .where(UserModelConfig.user_id == user_id)
            .where(UserModelConfig.model_type == model_type)
        )
        config = result.scalar_one_or_none()
        
        if not config:
            logger.warning(f"No {model_type} config for user {user_id}")
            return None
        
        # 2. 加载关联的 UserProvider
        await session.refresh(config, ["provider"])
        user_provider = config.provider
        
        if not user_provider or not user_provider.is_active:
            logger.warning(f"Provider inactive for user {user_id}")
            return None
        
        # 3. 加载模板
        await session.refresh(user_provider, ["template"])
        template = user_provider.template
        
        # 4. 解密 API Key
        api_key = None
        if user_provider.api_key_encrypted:
            try:
                api_key = user_provider_manager.decrypt_key(user_provider.api_key_encrypted)
                logger.debug(f"[Config] Successfully decrypted API key for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to decrypt key: {type(e).__name__}: {str(e)}")
                logger.error(f"  Encrypted key preview: {user_provider.api_key_encrypted[:30]}...")
                return None
        
        api_base = user_provider.custom_config.get("api_base") or template.api_base
        extra_config = {**template.config_schema, **user_provider.custom_config}
        provider_type = template.provider_type  # 获取 provider_type
        
        return (config.default_model_name, api_key, api_base, extra_config, provider_type)

async def completion(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    user_id: str = "default_user",
    **kwargs
) -> Any:
    """
    LLM 补全（多租户版本）。
    
    Args:
        messages: 对话消息列表
        model: 模型名称（可选，不指定则使用用户默认）
        user_id: 用户 ID
        **kwargs: 传递给 LiteLLM 的其他参数
    """
    # 1. 获取用户配置
    config = await get_user_model_config(user_id, "llm")
    
    if not config:
        raise ValueError(f"User {user_id} has no LLM configured. Please run /users/init first.")
    
    model_name, api_key, api_base, extra_config, provider_type = config
    
    # 如果指定了模型，使用指定的；否则使用默认
    final_model = model or model_name
    
    # 2. 调用 LiteLLM
    try:
        # 构建调用参数
        call_kwargs = {
            "model": final_model,
            "messages": messages,
            **kwargs
        }
        
        # 添加 API 配置
        if api_key:
            call_kwargs["api_key"] = api_key
        if api_base:
            call_kwargs["api_base"] = api_base
        
        # 重要：对于兼容 OpenAI API 的供应商，需要指定 custom_llm_provider
        if provider_type and provider_type != "openai":
            call_kwargs["custom_llm_provider"] = provider_type
        elif api_base and "openai.com" not in api_base:
            # OpenAI 兼容 API
            call_kwargs["custom_llm_provider"] = "openai"
        
        response = await litellm.acompletion(**call_kwargs)
        return response
    except Exception as e:
        logger.error(f"LLM completion failed: {e}")
        raise

async def embedding(
    input: Union[str, List[str]],
    model: Optional[str] = None,
    user_id: str = "default_user"
) -> Dict[str, Any]:
    """
    向量嵌入（多租户版本）。
    
    Args:
        input: 输入文本
        model: 模型名称（可选）
        user_id: 用户 ID
    """
    config = await get_user_model_config(user_id, "embedding")
    
    if not config:
        logger.warning(f"User {user_id} has no embedding config, using default")
        # Fallback：使用全局配置
        return await litellm.aembedding(
            model=model or "text-embedding-3-small",
            input=input
        )
    
    model_name, api_key, api_base, _, provider_type = config
    final_model = model or model_name
    
    try:
        call_kwargs = {
            "model": final_model,
            "input": input
        }
        
        if api_key:
            call_kwargs["api_key"] = api_key
        if api_base:
            call_kwargs["api_base"] = api_base
        
        # 同样需要设置 provider
        if provider_type and provider_type != "openai":
            call_kwargs["custom_llm_provider"] = provider_type
        elif api_base and "openai.com" not in api_base:
            call_kwargs["custom_llm_provider"] = "openai"
        
        response = await litellm.aembedding(**call_kwargs)
        return response
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise
