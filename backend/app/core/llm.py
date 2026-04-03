from typing import Any, Dict, List, Optional, Union
import litellm
from app.core.config import settings
from app.core.db import SessionLocal
from app.models.provider import UserProvider, UserModelConfig, ProviderTemplate
from app.services.user_provider_manager import user_provider_manager
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)

# 厂牌别名映射：解决 LiteLLM 原生库代号与用户习惯名称的差异
LITELLM_PROVIDER_MAP = {
    "qwen": "dashscope",
    "通义千问": "dashscope",
    "zhipu": "zhipuai",
    "智谱": "zhipuai",
    "glm": "zhipuai",
}

def _clean_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """递归清理消息中的无效字段，并确保 Tool 协议合规与自愈"""
    initial_cleaned = []
    for msg in messages:
        # 深度复制并移除所有 None 字段
        m = {k: v for k, v in msg.items() if v is not None}
        
        role = m.get("role")
        
        # 1. 移除空的 tool_calls 列表
        if "tool_calls" in m and (not m["tool_calls"] or len(m["tool_calls"]) == 0):
            m.pop("tool_calls")
            
        # 2. 补全 user 消息必填的 content
        if role == "user" and "content" not in m:
            m["content"] = ""
            
        # 3. 补全 tool 消息必填的 content 避免 OpenAI 400
        if role == "tool" and "content" not in m:
            m["content"] = ""
            
        # 4. 强制处理 tool_call_id
        if role == "tool" and "tool_call_id" not in m:
            continue # 丢弃非法的 tool 响应
            
        initial_cleaned.append(m)
    
    # --- 核心协议自愈 (Core Protocol Healing) ---
    # 规则：带 tool_calls 的 assistant 消息后必须紧跟所有对应的 tool 响应，中间不能断开
    final_cleaned = []
    i = 0
    while i < len(initial_cleaned):
        msg = initial_cleaned[i]
        
        if msg.get("role") == "assistant" and "tool_calls" in msg:
            tool_calls = msg["tool_calls"]
            expected_ids = {tc.get("id") for tc in tool_calls if tc.get("id")}
            
            # 向后探测后续是否紧跟了对应的 tool 消息
            j = i + 1
            received_ids = set()
            while j < len(initial_cleaned) and initial_cleaned[j].get("role") == "tool":
                tid = initial_cleaned[j].get("tool_call_id")
                if tid:
                    received_ids.add(tid)
                j += 1
            
            # 如果不完全匹配 (或者是空的)，说明协议序列在地平线处断裂了 (例如由于会话中断导致)
            if not expected_ids.issubset(received_ids):
                # 协议自愈：剥离 tool_calls，将其降级为普通消息回复
                msg.pop("tool_calls")
                if not msg.get("content"):
                    msg["content"] = "[系统提示：工具调用由于会话中断已重置]"
        
        final_cleaned.append(msg)
        i += 1
        
    return final_cleaned

# 配置 LiteLLM 全局回退（如果有）
if hasattr(settings, 'OPENAI_API_KEY') and settings.OPENAI_API_KEY:
    litellm.api_key = settings.OPENAI_API_KEY

async def get_user_model_config(
    user_id: str,
    model_type: str = "llm"
) -> tuple[str, str, str, dict, str] | None:
    """
    获取用户的默认模型配置。
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
        
        # 2. 获取该提供者的具体配置
        provider_config = await get_provider_config(config.provider_id)
        if not provider_config:
            return None
            
        api_key, api_base, extra_config, provider_type = provider_config
        return (config.default_model_name, api_key, api_base, extra_config, provider_type)

async def get_provider_config(
    provider_id: int
) -> tuple[str, str, dict, str] | None:
    """
    获取特定供应商的连接配置。
    Returns: (api_key, api_base, extra_config, provider_type)
    """
    async with SessionLocal() as session:
        result = await session.execute(
            select(UserProvider).where(UserProvider.id == provider_id)
        )
        user_provider = result.scalar_one_or_none()
        
        if not user_provider or not user_provider.is_active:
            return None
            
        await session.refresh(user_provider, ["template"])
        template = user_provider.template
        
        # 解密 API Key
        api_key = None
        if user_provider.api_key_encrypted:
            try:
                api_key = user_provider_manager.decrypt_key(user_provider.api_key_encrypted)
            except Exception as e:
                logger.error(f"Failed to decrypt key for provider {provider_id}: {e}")
                return None
        
        api_base = user_provider.custom_config.get("api_base") if user_provider.custom_config else None
        api_base = api_base or (template.api_base if template else None)
        
        schema = (template.config_schema if template else {}) or {}
        custom = user_provider.custom_config or {}
        extra_config = {**schema, **custom}
        provider_type = template.provider_type if template else "openai"
        
        return (api_key, api_base, extra_config, provider_type)

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
    # 1. 获取配置基础
    # 优先使用传入的凭据，否则获取用户默认配置
    if kwargs.get("api_key") or kwargs.get("api_base"):
        model_name = model or settings.DEFAULT_LLM_MODEL
        api_key = kwargs.pop("api_key", None)
        api_base = kwargs.pop("api_base", None)
        extra_config = {}
        provider_type = kwargs.pop("custom_llm_provider", "openai")
    else:
        config = await get_user_model_config(user_id, "llm")
        if not config:
            if not settings.DEFAULT_LLM_PROVIDER:
                raise ValueError(f"User {user_id} has no LLM configured and DEFAULT_LLM_PROVIDER is empty.")
            config = (
                settings.DEFAULT_LLM_MODEL, 
                settings.DEFAULT_LLM_API_KEY, 
                getattr(settings, "DEFAULT_LLM_API_BASE", None), 
                {}, 
                settings.DEFAULT_LLM_PROVIDER
            )
        model_name, api_key, api_base, extra_config, provider_type = config
    
    # 确定最终模型名，并确保其不为 None
    model_name_base = model_name or settings.DEFAULT_LLM_MODEL or "gpt-3.5-turbo"
    final_model = model if model and model != "default" else model_name_base
    
    # 2. 调用 LiteLLM
    try:
        if not final_model or not isinstance(final_model, str):
            logger.error(f"[LLM] final_model is invalid: {final_model}")
            raise ValueError("No valid LLM model name specified.")

        clean_model = final_model.split("/")[-1] if "/" in final_model else final_model
        
        call_kwargs = {
            "model": final_model,
            "messages": messages,
            **kwargs
        }
        
        if api_key:
            call_kwargs["api_key"] = api_key
            
        _pt = provider_type.lower() if provider_type else ""
        
        if api_base:
            call_kwargs["api_base"] = api_base
            if "openai.com" not in api_base:
                call_kwargs["custom_llm_provider"] = "openai"
            call_kwargs["model"] = final_model.split("/")[-1] if "/" in final_model else final_model
        else:
            # 没有被环境指定专门代理的，扔给 LiteLLM 原生解析
            mapped_pt = LITELLM_PROVIDER_MAP.get(_pt, _pt)
            
            # 特殊处理：LiteLLM 对 Qwen 的原生支持需要 'dashscope/' 前缀或对应的 custom_llm_provider
            if mapped_pt == "dashscope" and "/" not in clean_model:
                call_kwargs["model"] = f"dashscope/{clean_model}"
                # 这种情况下不需要再传 custom_llm_provider，前缀已足够识别
            else:
                if mapped_pt and mapped_pt != "openai":
                    call_kwargs["custom_llm_provider"] = mapped_pt
                call_kwargs["model"] = final_model  # 保留原始路径
            
        logger.info(f"[LLM] Calling litellm.acompletion with model: {call_kwargs.get('model')}")
        response = await litellm.acompletion(**call_kwargs)
        logger.info("[LLM] litellm.acompletion returned")
        return response
    except Exception as e:
        logger.error(f"[LLM] completion failed: {type(e).__name__}: {e}")
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
        # [Fallback Stateless Mode] 确保 fallback 至少有一个安全的默认字符串
        def_model = getattr(settings, "DEFAULT_EMBEDDING_MODEL", None) or "text-embedding-3-small"
        def_key = getattr(settings, "DEFAULT_EMBEDDING_API_KEY", None) or getattr(settings, "DEFAULT_LLM_API_KEY", "")
        def_base = getattr(settings, "DEFAULT_EMBEDDING_API_BASE", None) or getattr(settings, "DEFAULT_LLM_API_BASE", None)
        def_provider = getattr(settings, "DEFAULT_EMBEDDING_PROVIDER", None) or getattr(settings, "DEFAULT_LLM_PROVIDER", "openai")
        
        config = (def_model, def_key, def_base, {}, def_provider)
    
    model_name, api_key, api_base, _, provider_type = config
    final_model = model if model and model != "default" else (model_name or "text-embedding-3-small")
    
    try:
        if not final_model or not isinstance(final_model, str):
            logger.error(f"[LLM] final_embedding_model is invalid: {final_model}")
            raise ValueError("No valid Embedding model name specified.")

        call_kwargs = {
            "model": final_model,
            "input": input,
            "encoding_format": "float"  # 强制指定，解决部分 OAI 兼容接口的 400 报错
        }
        
        if api_key:
            call_kwargs["api_key"] = api_key
            
        clean_model = final_model.split("/")[-1] if "/" in final_model else final_model
        _pt = provider_type.lower() if provider_type else ""
        
        if api_base:
            call_kwargs["api_base"] = api_base
            # 安全检查：防止 api_base 为 None 导致 in 操作符报错
            if api_base and "openai.com" not in api_base:
                call_kwargs["custom_llm_provider"] = "openai"
            call_kwargs["model"] = final_model.split("/")[-1] if "/" in final_model else final_model
        else:
            mapped_pt = LITELLM_PROVIDER_MAP.get(_pt, _pt)
            
            if mapped_pt == "dashscope" and "/" not in clean_model:
                call_kwargs["model"] = f"dashscope/{clean_model}"
            else:
                if mapped_pt and mapped_pt != "openai":
                    call_kwargs["custom_llm_provider"] = mapped_pt
                call_kwargs["model"] = final_model
        
        response = await litellm.aembedding(**call_kwargs)
        return response
    except Exception as e:
        # 如果是未配置导致的错误，记录为 Warning 而非 Error 减少日志干扰
        if "No valid Embedding model" in str(e):
            logger.warning(f"[LLM] Embedding skipped due to missing config: {e}")
        else:
            logger.error(f"[LLM] Embedding failed: {e}")
        raise
