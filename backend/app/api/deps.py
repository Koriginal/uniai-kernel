from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.db import get_db
from app.models.user import User, UserApiKey
from app.services.user_service import user_service
from datetime import datetime

# OAuth2 方案，用于 Dashboard 登录
reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"/api/v1/auth/login"
)

async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(reusable_oauth2),
    request: Request = None
) -> User:
    """
    Dashboard 专用的 JWT 鉴权依赖项
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_current_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="The user doesn't have enough privileges"
        )
    return current_user

async def get_identity(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> str:
    """
    通用身份识别（混合模式）：优先检查 Authorization Bearer，其次检查 X-API-Key。
    未通过鉴权时默认拒绝；仅在显式开启 ALLOW_ANONYMOUS_ADMIN_FALLBACK 时回退 admin。
    用于 /chat/completions 等双向接口。
    """
    # 默认身份上下文
    if request is not None:
        request.state.identity_context = {
            "source": "fallback",
            "api_key_id": None,
            "api_key_name": None,
            "user_id": None,
        }

    # 1. 检查 JWT (Bearer)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
            user = await db.get(User, user_id)
            if not user or not user.is_active:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive user")
            if request is not None:
                request.state.identity_context = {
                    "source": "dashboard_jwt",
                    "api_key_id": None,
                    "api_key_name": None,
                    "user_id": user_id,
                }
            return user_id
        except (JWTError, HTTPException):
            pass # 继续尝试 API Key

    # 2. 检查 API Key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        result = await db.execute(
            select(UserApiKey).where(UserApiKey.key == api_key).where(UserApiKey.is_active == True)
        )
        api_key_obj = result.scalar_one_or_none()
        if api_key_obj:
            api_key_obj.last_used_at = datetime.utcnow()
            await db.commit()
            user = await db.get(User, api_key_obj.user_id)
            if user:
                if request is not None:
                    request.state.identity_context = {
                        "source": "api_key",
                        "api_key_id": api_key_obj.id,
                        "api_key_name": api_key_obj.name,
                        "user_id": user.id,
                    }
                return user.id

    # 3. 可选演示回退
    if settings.ALLOW_ANONYMOUS_ADMIN_FALLBACK:
        if request is not None:
            request.state.identity_context = {
                "source": "fallback",
                "api_key_id": None,
                "api_key_name": None,
                "user_id": "admin",
            }
        return "admin"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: provide Authorization Bearer token or X-API-Key",
    )
