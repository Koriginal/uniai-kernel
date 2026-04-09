from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User, UserApiKey
import secrets
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class UserService:
    async def create_user(self, db: AsyncSession, email: str, username: str = None) -> User:
        user = User(email=email, username=username)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    async def create_api_key(self, db: AsyncSession, user_id: str, name: str = "Default Key") -> str:
        # 生成 32 位随机 Key (ak-...)
        raw_key = f"sk-{secrets.token_urlsafe(32)}"
        
        api_key = UserApiKey(
            user_id=user_id,
            key=raw_key,
            name=name
        )
        db.add(api_key)
        await db.commit()
        return raw_key

    async def get_user_by_api_key(self, db: AsyncSession, key: str) -> Optional[User]:
        result = await db.execute(
            select(UserApiKey).where(UserApiKey.key == key).where(UserApiKey.is_active == True)
        )
        api_key = result.scalar_one_or_none()
        if api_key:
            api_key.last_used_at = datetime.utcnow()
            await db.commit()
            return await db.get(User, api_key.user_id)
        return None

user_service = UserService()
