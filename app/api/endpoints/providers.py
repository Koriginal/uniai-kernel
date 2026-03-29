from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_db
from app.core.auth import get_current_user_id
from app.services.user_provider_manager import user_provider_manager
from app.models.provider import ProviderTemplate
from pydantic import BaseModel
from typing import Optional, Dict, List

router = APIRouter()

# ============================================================================
# Pydantic Models
# ============================================================================

class UserProviderCreate(BaseModel):
    """用户创建供应商配置"""
    template_name: str  # e.g., "OpenAI", "DeepSeek"
    api_key: Optional[str] = None
    custom_config: Optional[Dict] = {}

class DefaultModelSet(BaseModel):
    """设置默认模型"""
    model_type: str  # llm, embedding, tts, stt
    model_name: str
    provider_id: int

# ============================================================================
# 系统级接口（查看可用模板）
# ============================================================================

@router.get("/templates", summary="查看供应商模板")
async def list_provider_templates(db: AsyncSession = Depends(get_db)):
    """
    获取所有可用的供应商模板。
    包括免费和付费选项。
    """
    result = await db.execute(
        select(ProviderTemplate).where(ProviderTemplate.is_active == True)
    )
    templates = result.scalars().all()
    
    return [
        {
            "id": t.id,
            "name": t.name,
            "type": t.provider_type,
            "is_free": t.is_free,
            "requires_api_key": t.requires_api_key,
            "description": t.description,
            "supported_models": t.supported_models
        }
        for t in templates
    ]

# ============================================================================
# 用户级接口（配置自己的供应商）
# ============================================================================

@router.post("/my/providers", summary="配置我的供应商")
async def create_my_provider(
    provider: UserProviderCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    用户配置自己的供应商。
    
    示例：
    ```json
    {
      "template_name": "OpenAI",
      "api_key": "sk-xxx"
    }
    ```
    """
    try:
        user_provider = await user_provider_manager.create_user_provider(
            db, user_id, provider.template_name, provider.api_key, provider.custom_config
        )
        return {
            "id": user_provider.id,
            "template_id": user_provider.template_id,
            "is_active": user_provider.is_active
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/my/providers", summary="我的供应商列表")
async def list_my_providers(
    user_id: str = "default_user",
    db: AsyncSession = Depends(get_db)
):
    """查看我配置的所有供应商"""
    providers = await user_provider_manager.get_user_providers(db, user_id)
    
    result = []
    for p in providers:
        await db.refresh(p, ["template"])
        result.append({
            "id": p.id,
            "template_name": p.template.name,
            "template_type": p.template.provider_type,
            "is_free": p.template.is_free,
            "supported_models": p.template.supported_models,
            "is_active": p.is_active
        })
    
    return result

# ============================================================================
# 默认模型配置
# ============================================================================

@router.put("/my/default-models", summary="设置默认模型")
async def set_default_model(
    config: DefaultModelSet,
    user_id: str = "default_user",
    db: AsyncSession = Depends(get_db)
):
    """
    设置各类任务的默认模型。
    
    示例：
    ```json
    {
      "model_type": "llm",
      "model_name": "gpt-4",
      "provider_id": 1
    }
    ```
    """
    result = await user_provider_manager.set_default_model(
        db, user_id, config.model_type, config.model_name, config.provider_id
    )
    return {
        "model_type": result.model_type,
        "model_name": result.default_model_name,
        "provider_id": result.provider_id
    }

@router.get("/my/default-models", summary="查看默认模型")
async def get_my_default_models(
    user_id: str = "default_user",
    db: AsyncSession = Depends(get_db)
):
    """查看我的默认模型配置"""
    from sqlalchemy import select
    from app.models.provider import UserModelConfig
    
    result = await db.execute(
        select(UserModelConfig).where(UserModelConfig.user_id == user_id)
    )
    configs = result.scalars().all()
    
    return [
        {
            "model_type": c.model_type,
            "model_name": c.default_model_name,
            "provider_id": c.provider_id
        }
        for c in configs
    ]
