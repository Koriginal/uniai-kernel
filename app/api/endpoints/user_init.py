"""
用户初始化 API
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.services.user_init_service import init_new_user

router = APIRouter()

@router.post("/init", summary="初始化新用户")
async def initialize_user(
    user_id: str = "default_user",
    db: AsyncSession = Depends(get_db)
):
    """
    初始化新用户，自动分配免费试用模型。
    
    新用户首次访问时调用，系统会自动：
    1. 分配免费供应商（DeepSeek/Groq）
    2. 设置默认 LLM 模型
    """
    result = await init_new_user(db, user_id)
    return result
