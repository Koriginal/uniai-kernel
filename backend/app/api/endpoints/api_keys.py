from fastapi import APIRouter, Depends, HTTPException, Body
from app.api import deps
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from app.core.db import get_db
from app.models.user import UserApiKey, User
from app.services.user_service import user_service
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class ApiKeyCreate(BaseModel):
    name: str = "Default Key"

class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key: str # 仅在创建时返回完整 key，或后续脱敏
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]

    class Config:
        from_attributes = True

@router.get("/", response_model=List[ApiKeyResponse])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """获取当前登录用户的所有 API 秘钥"""
    result = await db.execute(
        select(UserApiKey).where(UserApiKey.user_id == current_user.id)
    )
    return result.scalars().all()

@router.post("/", response_model=ApiKeyResponse)
async def create_api_key(
    data: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """为当前用户新建一个 API 秘钥"""
    raw_key = await user_service.create_api_key(db, current_user.id, data.name)
    
    # 获取刚刚创建的对象
    result = await db.execute(
        select(UserApiKey).where(UserApiKey.key == raw_key)
    )
    return result.scalar_one()

@router.delete("/{key_id}")
async def delete_api_key(key_id: str, db: AsyncSession = Depends(get_db)):
    """删除/吊销 API 秘钥"""
    api_key = await db.get(UserApiKey, key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key not found")
    
    await db.delete(api_key)
    await db.commit()
    return {"status": "success", "message": "API Key revoked"}
