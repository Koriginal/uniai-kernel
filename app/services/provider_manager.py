from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.provider import Provider, AIModel
from app.core.config import settings
from cryptography.fernet import Fernet
import json
import base64
import os

# 如果不存在密钥，则生成一个，或者从 env 中使用
# 在生产环境中，这应该是一个持久的环境变量
SECRET_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
cipher = Fernet(SECRET_KEY.encode())

class ProviderManager:
    async def add_provider(self, session: AsyncSession, name: str, type: str, api_base: str, api_key: str, extra_config: dict = {}):
        encrypted_key = cipher.encrypt(api_key.encode()).decode()
        provider = Provider(
            provider_name=name,
            provider_type=type,
            api_base=api_base,
            api_key_encrypted=encrypted_key,
            extra_config=extra_config
        )
        session.add(provider)
        await session.commit()
        await session.refresh(provider)
        return provider

    async def get_provider(self, session: AsyncSession, provider_id: int):
        result = await session.execute(select(Provider).where(Provider.id == provider_id))
        return result.scalars().first()

    async def get_active_providers(self, session: AsyncSession):
        result = await session.execute(select(Provider).where(Provider.is_active == True))
        return result.scalars().all()

    def decrypt_key(self, encrypted_key: str) -> str:
        return cipher.decrypt(encrypted_key.encode()).decode()

    async def add_model(self, session: AsyncSession, name: str, provider_id: int, type: str, context_window: int = 4096):
        model = AIModel(
            model_name=name,
            provider_id=provider_id,
            model_type=type,
            context_window=context_window
        )
        session.add(model)
        await session.commit()
        await session.refresh(model)
        return model

    async def get_all_models(self, session: AsyncSession):
        result = await session.execute(select(AIModel))
        return result.scalars().all()

provider_manager = ProviderManager()
