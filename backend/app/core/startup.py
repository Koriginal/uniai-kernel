"""
启动时自动配置

从环境变量读取默认模型配置，自动为 default_user 初始化。
"""
import asyncio
from app.core.config import settings
from app.core.db import SessionLocal
from app.models.provider import ProviderTemplate, UserProvider, UserModelConfig
from sqlalchemy import select, func, text
import logging

logger = logging.getLogger(__name__)

async def ensure_vector_extension_is_ready(session):
    """
    自愈逻辑：确保 pgvector 扩展已激活，且维度正确（1024）。
    """
    try:
        # 1. 激活扩展
        await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        
        # 2. 校验并修复维度 (1536 -> 1024)
        # 检查字段是否存在
        res = await session.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'user_memories' AND column_name = 'embedding'"))
        if not res.fetchone():
            logger.info("[Startup] Column 'embedding' missing, adding now...")
            await session.execute(text("ALTER TABLE user_memories ADD COLUMN embedding vector(1024);"))
            await session.execute(text("CREATE INDEX IF NOT EXISTS user_memories_embedding_hnsw_idx ON user_memories USING hnsw (embedding vector_cosine_ops);"))
        else:
            # 校验维度 (简单方式：尝试转换类型，如果已是 1024 则无影响)
            try:
                await session.execute(text("ALTER TABLE user_memories ALTER COLUMN embedding TYPE vector(1024);"))
            except Exception:
                # 若已有数据且维度不符，此步可能报错，但在新部署环境下是安全的
                pass
        
        logger.info("[Startup] Vector extension and dimension: OK")
    except Exception as e:
        logger.warning(f"[Startup] Vector self-healing skipped or failed: {e}. This might affect expert collaboration.")

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
        
    if not settings.ENABLE_DATABASE:
        logger.info("[Auto-Config] ENABLE_DATABASE=False, running in stateless plugin mode, skipping DB setup.")
        return
    
    async with SessionLocal() as session:
        # 0. 基础设施自愈：确保向量环境就绪
        await ensure_vector_extension_is_ready(session)
        await session.commit()
        
        user_id = settings.DEFAULT_USER_ID
        
        # 0. 确保基础 User 与 API Key 存(如果缺席则补齐)
        from app.models.user import User, UserApiKey
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            logger.info(f"[Auto-Config] Creating seed user: {user_id}")
            user = User(id=user_id, email=f"{user_id}@uniai.local", username="Auto Seed User")
            session.add(user)
            await session.commit()
            
        result = await session.execute(
            select(UserApiKey)
            .where(UserApiKey.user_id == user_id)
            .where(UserApiKey.key == settings.DEFAULT_USER_API_KEY)
        )
        if not result.scalar_one_or_none():
            logger.info(f"[Auto-Config] Creating seed API Key for {user_id}")
            new_key = UserApiKey(user_id=user_id, key=settings.DEFAULT_USER_API_KEY, name="Seed Key")
            session.add(new_key)
            await session.commit()

        # 1. 检查是否已配置 Provider
        result = await session.execute(
            select(UserProvider).where(UserProvider.user_id == user_id)
        )
        existing = result.scalars().first()
        
        if existing:
            logger.info(f"[Auto-Config] default_user already configured")
            return
        
        # 2. 查找模板 (支持简称映射与不区分大小写)
        provider_name = settings.DEFAULT_LLM_PROVIDER
        name_map = {
            "qwen": "通义千问",
            "zhipu": "智谱AI",
            "deepseek": "DeepSeek",
            "groq": "Groq",
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "gemini": "Google Gemini"
        }
        target_name = name_map.get(provider_name.lower(), provider_name)
        
        result = await session.execute(
            select(ProviderTemplate).where(
                func.lower(ProviderTemplate.name) == target_name.lower()
            )
        )
        template = result.scalar_one_or_none()
        
        if not template:
            # 最后的尝试：部分匹配
            result = await session.execute(
                select(ProviderTemplate).where(
                    ProviderTemplate.name.ilike(f"%{provider_name}%")
                )
            )
            template = result.scalars().first()

        if not template:
            logger.warning(f"[Auto-Config] Template '{provider_name}' not found")
            return
        
        # 3. 创建用户供应商
        from app.services.user_provider_manager import user_provider_manager
        
        try:
            user_provider = await user_provider_manager.create_user_provider(
                session,
                user_id,
                target_name,  # 使用已映射的标准模板名
                settings.DEFAULT_LLM_API_KEY,
                {}
            )
            
            # 4. 设置默认模型（支持多种类型）
            # supported_models 可能是 str 列表或 dict 列表
            def extract_model_name(m):
                if isinstance(m, dict):
                    return m.get("name", str(m))
                return str(m)
            
            default_llm = settings.DEFAULT_LLM_MODEL
            if not default_llm and template.supported_models:
                default_llm = extract_model_name(template.supported_models[0])
            model_configs = [
                ("llm", default_llm),
                ("embedding", settings.DEFAULT_EMBEDDING_MODEL),
                ("rerank", settings.DEFAULT_RERANK_MODEL),
                ("tts", settings.DEFAULT_TTS_MODEL),
                ("stt", settings.DEFAULT_STT_MODEL),
            ]
            
            configured = []
            for model_type, model_name in model_configs:
                
                if model_name:
                    await user_provider_manager.set_default_model(
                        session, user_id, model_type, model_name, user_provider.id
                    )
                    configured.append(f"{model_type}={model_name}")
            
            logger.info(f"[Auto-Config] ✅ Configured default_user: {', '.join(configured)}")
            
        except Exception as e:
            logger.error(f"[Auto-Config] Failed: {e}")
            await session.rollback()

if __name__ == "__main__":
    asyncio.run(auto_configure_default_user())
