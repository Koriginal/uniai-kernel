from typing import List, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_db
from app.models.user import User
from app.api import deps
from app.core.security import get_password_hash
from pydantic import BaseModel, EmailStr

router = APIRouter()

class UserCreate(BaseModel):
    email: str
    username: str
    phone: Optional[str] = None
    password: str
    is_admin: bool = False

class UserUpdate(BaseModel):
    email: str = None
    username: str = None
    phone: str = None
    bio: str = None
    avatar: str = None
    preferences: dict = None
    password: str = None
    is_admin: bool = None
    is_active: bool = None

class UserPasswordUpdate(BaseModel):
    old_password: str
    new_password: str

class UserOut(BaseModel):
    id: str
    email: str
    username: str
    phone: Optional[str] = None
    bio: Optional[str] = None
    avatar: Optional[str] = None
    preferences: Optional[dict] = None
    is_admin: bool
    is_active: bool
    created_at: datetime

@router.get("/", response_model=List[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> Any:
    """获取所有用户列表（仅限管理员）"""
    result = await db.execute(select(User))
    return result.scalars().all()

@router.post("/", response_model=UserOut)
async def create_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserCreate,
    current_user: User = Depends(deps.get_current_admin),
) -> Any:
    """创建新用户（仅限管理员）"""
    result = await db.execute(select(User).where(User.email == user_in.email))
    user = result.scalar_one_or_none()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )
    
    db_obj = User(
        email=user_in.email,
        username=user_in.username,
        phone=user_in.phone,
        hashed_password=get_password_hash(user_in.password),
        is_admin=user_in.is_admin,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

@router.delete("/{user_id}", response_model=dict)
async def delete_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_id: str,
    current_user: User = Depends(deps.get_current_admin),
) -> Any:
    """删除用户（仅限管理员）"""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Users cannot delete themselves")
    
    await db.delete(user)
    await db.commit()
    return {"status": "success", "message": "User deleted"}

@router.post("/me/change-password")
async def change_password(
    *,
    db: AsyncSession = Depends(get_db),
    password_in: UserPasswordUpdate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """修改当前登录用户的密码"""
    from app.core.security import verify_password
    
    if not verify_password(password_in.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect old password",
        )
    
    current_user.hashed_password = get_password_hash(password_in.new_password)
    db.add(current_user)
    await db.commit()
    return {"status": "success", "message": "Password updated successfully"}

@router.patch("/me", response_model=UserOut)
async def update_user_me(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserUpdate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """更新当前登录用户的个人资料"""
    if user_in.username is not None:
        current_user.username = user_in.username
    if user_in.phone is not None:
        current_user.phone = user_in.phone
    if user_in.bio is not None:
        current_user.bio = user_in.bio
    if user_in.avatar is not None:
        current_user.avatar = user_in.avatar
    if user_in.preferences is not None:
        # 如果提供了 preferences，进行合并或替换
        if current_user.preferences is None:
            current_user.preferences = {}
        # 简单替换策略，或者可以使用 deep_merge
        current_user.preferences = {**current_user.preferences, **user_in.preferences}
        
    if user_in.email is not None:
        current_user.email = user_in.email
    if user_in.password is not None:
        current_user.hashed_password = get_password_hash(user_in.password)
        
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user
