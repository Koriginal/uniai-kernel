from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.provider import ProviderTemplate, UserProvider, UserModelConfig
from app.core.config import settings
from cryptography.fernet import Fernet
import os
import logging

logger = logging.getLogger(__name__)

class UserProviderManager:
    """用户级供应商管理"""
    
    def __init__(self):
        """初始化时不固定密钥"""
        self._cipher = None
    
    def _get_cipher(self):
        """动态获取加密器（确保使用最新的 ENCRYPTION_KEY）"""
        from cryptography.fernet import Fernet
        from app.core.config import settings
        
        # 每次都重新读取，确保获取最新值
        secret_key = settings.ENCRYPTION_KEY
        if not secret_key or secret_key.strip() == "":
            logger.error("[Security] ENCRYPTION_KEY not set in config!")
            raise ValueError("ENCRYPTION_KEY must be set in .env")
        
        logger.debug(f"[Cipher] Using ENCRYPTION_KEY: {secret_key[:10]}...")
        return Fernet(secret_key.encode())
    
    async def create_user_provider(
        self, 
        session: AsyncSession, 
        user_id: str, 
        template_name: str, 
        api_key: str = None,
        custom_config: dict = {}
    ) -> UserProvider:
        """
        为用户创建供应商配置。
        
        Args:
            user_id: 用户 ID
            template_name: 供应商模板名称
            api_key: 用户的 API Key（如果需要）
            custom_config: 自定义配置
        """
        # 1. 查找模板
        result = await session.execute(
            select(ProviderTemplate).where(ProviderTemplate.name == template_name)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise ValueError(f"供应商模板 '{template_name}' 不存在")
        
        # 2. 检查是否需要 API Key
        if template.requires_api_key and not api_key:
            raise ValueError(f"{template_name} 需要提供 API Key")
        
        # 3. 加密 API Key
        encrypted_key = None
        if api_key:
            encrypted_key = self._get_cipher().encrypt(api_key.encode()).decode()
        
        # 4. 创建用户供应商
        user_provider = UserProvider(
            user_id=user_id,
            template_id=template.id,
            api_key_encrypted=encrypted_key,
            custom_config=custom_config
        )
        session.add(user_provider)
        await session.commit()
        await session.refresh(user_provider)
        
        return user_provider
    
    async def get_user_providers(
        self, 
        session: AsyncSession, 
        user_id: str
    ) -> list[UserProvider]:
        """获取用户的所有供应商配置"""
        result = await session.execute(
            select(UserProvider)
            .where(UserProvider.user_id == user_id)
            .where(UserProvider.is_active == True)
        )
        return list(result.scalars().all())
    
    async def set_default_model(
        self,
        session: AsyncSession,
        user_id: str,
        model_type: str,  # llm, embedding, tts, stt
        model_name: str,
        provider_id: int
    ) -> UserModelConfig:
        """设置用户的默认模型"""
        # 检查是否已存在
        result = await session.execute(
            select(UserModelConfig)
            .where(UserModelConfig.user_id == user_id)
            .where(UserModelConfig.model_type == model_type)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            # 更新
            existing.default_model_name = model_name
            existing.provider_id = provider_id
            config = existing
        else:
            # 创建
            config = UserModelConfig(
                user_id=user_id,
                model_type=model_type,
                default_model_name=model_name,
                provider_id=provider_id
            )
            session.add(config)
        
        await session.commit()
        await session.refresh(config)
        return config
    
    async def get_user_default_model(
        self,
        session: AsyncSession,
        user_id: str,
        model_type: str
    ) -> tuple[str, UserProvider] | None:
        """获取用户默认模型配置"""
        result = await session.execute(
            select(UserModelConfig)
            .where(UserModelConfig.user_id == user_id)
            .where(UserModelConfig.model_type == model_type)
        )
        config = result.scalar_one_or_none()
        
        if not config:
            return None
        
        # 加载关联的 provider
        await session.refresh(config, ["provider"])
        return (config.default_model_name, config.provider)
    
    def decrypt_key(self, encrypted_key: str) -> str:
        """解密 API Key"""
        return self._get_cipher().decrypt(encrypted_key.encode()).decode()

user_provider_manager = UserProviderManager()
