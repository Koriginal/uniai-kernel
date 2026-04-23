from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.db import get_db
from app.api import deps
from app.services.user_provider_manager import user_provider_manager
from app.models.provider import ProviderTemplate, UserProvider, ProviderModel, UserModelConfig
from app.core.llm import completion
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Literal
from sqlalchemy.exc import IntegrityError
import time

router = APIRouter()

# ============================================================================
# Pydantic Models
# ============================================================================

class UserProviderCreate(BaseModel):
    """用户创建供应商配置"""
    template_name: Optional[str] = None  # 从模板快捷接入
    display_name: Optional[str] = None  # 自定义名称
    api_base: Optional[str] = None  # 自定义 API Base（覆写模板）
    api_key: Optional[str] = None
    custom_config: Optional[Dict] = Field(default_factory=dict)

class ModelCreate(BaseModel):
    """在供应商下添加模型"""
    model_name: str
    model_type: Literal["llm", "embedding", "rerank", "vision", "reasoning", "tts", "stt"] = "llm"
    context_length: int = Field(default=4096, ge=128, le=2000000)
    max_output_tokens: Optional[int] = None
    is_default: bool = False

class DefaultModelSet(BaseModel):
    model_type: Literal["llm", "embedding", "rerank", "vision", "reasoning", "tts", "stt"]
    model_name: str
    provider_id: int


ALLOWED_DEFAULT_MODEL_TYPES = {"llm", "embedding", "rerank", "vision", "reasoning", "tts", "stt"}


async def _get_owned_provider(db: AsyncSession, user_id: str, provider_id: int) -> UserProvider:
    result = await db.execute(
        select(UserProvider)
        .where(
            UserProvider.id == provider_id,
            UserProvider.user_id == user_id,
            UserProvider.is_active == True,
        )
        .options(selectinload(UserProvider.template), selectinload(UserProvider.models))
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider

# ============================================================================
# 系统级接口
# ============================================================================

@router.get("/templates", summary="查看供应商模板")
async def list_provider_templates(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(deps.get_identity),
):
    """获取所有可用的供应商模板（含模型列表和上下文长度）。"""
    result = await db.execute(
        select(ProviderTemplate).where(ProviderTemplate.is_active == True)
    )
    templates = result.scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "type": t.provider_type,
            "api_base": t.api_base,
            "is_free": t.is_free,
            "requires_api_key": t.requires_api_key,
            "description": t.description,
            "supported_models": t.supported_models,
            "config_schema": t.config_schema
        }
        for t in templates
    ]

# ============================================================================
# 用户供应商 CRUD
# ============================================================================

@router.post("/my/providers", summary="接入供应商")
async def create_my_provider(
    provider: UserProviderCreate,
    user_id: str = Depends(deps.get_identity),
    db: AsyncSession = Depends(get_db)
):
    """
    接入供应商。支持两种模式：
    - 模板接入：指定 template_name，自动预填 API Base 和模型列表
    - 自定义接入：直接指定 api_base，不依赖模板
    """
    template = None
    if provider.template_name:
        result = await db.execute(
            select(ProviderTemplate).where(ProviderTemplate.name == provider.template_name)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise HTTPException(status_code=400, detail=f"模板 '{provider.template_name}' 不存在")
    
    # 加密 API Key
    encrypted_key = None
    if provider.api_key:
        encrypted_key = user_provider_manager._get_cipher().encrypt(provider.api_key.encode()).decode()

    # 计算最终的 API Base
    custom_api_base = provider.api_base or (template.api_base if template else None)
    if not custom_api_base:
        raise HTTPException(status_code=400, detail="API Base URL is required")

    # 同一用户下 display_name + api_base 组合去重，避免重复接入
    duplicate_check = await db.execute(
        select(UserProvider).where(
            UserProvider.user_id == user_id,
            UserProvider.is_active == True,
            UserProvider.display_name == (provider.display_name or (template.name if template else None)),
            UserProvider.custom_api_base == custom_api_base,
        )
    )
    if duplicate_check.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该供应商配置已存在，请勿重复接入")

    user_provider = UserProvider(
        user_id=user_id,
        template_id=template.id if template else None,
        display_name=provider.display_name or (template.name if template else None),
        custom_api_base=custom_api_base,
        api_key_encrypted=encrypted_key,
        custom_config=provider.custom_config or {}
    )
    db.add(user_provider)
    await db.commit()
    await db.refresh(user_provider)

    # 如果从模板接入，自动创建模板预置的模型
    if template and template.supported_models:
        models_data = template.supported_models
        for m in models_data:
            if isinstance(m, dict):
                model = ProviderModel(
                    provider_id=user_provider.id,
                    model_name=m.get("name", str(m)),
                    model_type=m.get("type", "llm"),
                    context_length=m.get("ctx", 4096),
                )
            else:
                model = ProviderModel(
                    provider_id=user_provider.id,
                    model_name=str(m),
                    model_type="llm",
                    context_length=4096,
                )
            db.add(model)
        await db.commit()

    return {"id": user_provider.id, "name": user_provider.effective_name, "status": "connected"}


@router.get("/my/providers", summary="我的供应商列表")
async def list_my_providers(
    user_id: str = Depends(deps.get_identity),
    db: AsyncSession = Depends(get_db)
):
    """查看我配置的所有供应商（含模型列表）"""
    result = await db.execute(
        select(UserProvider)
        .where(UserProvider.user_id == user_id, UserProvider.is_active == True)
        .options(selectinload(UserProvider.template), selectinload(UserProvider.models))
    )
    providers = result.scalars().all()
    
    out = []
    for p in providers:
        out.append({
            "id": p.id,
            "display_name": p.effective_name,
            "provider_type": p.template.provider_type if p.template else "openai",
            "api_base": p.effective_api_base,
            "description": p.template.description if p.template else None,
            "is_active": p.is_active,
            "has_api_key": bool(p.api_key_encrypted),
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "model_count": len(p.models or []),
            "models": [
                {
                    "id": m.id,
                    "model_name": m.model_name,
                    "model_type": m.model_type,
                    "context_length": m.context_length,
                    "max_output_tokens": m.max_output_tokens,
                    "is_default": m.is_default
                }
                for m in (p.models or [])
            ]
        })
    return out


@router.delete("/my/providers/{provider_id}", summary="删除供应商")
async def delete_my_provider(
    provider_id: int,
    user_id: str = Depends(deps.get_identity),
    db: AsyncSession = Depends(get_db)
):
    """删除用户的供应商配置（级联删除其下所有模型）"""
    provider = await _get_owned_provider(db, user_id, provider_id)
    await db.delete(provider)
    await db.commit()
    return {"status": "deleted", "id": provider_id}


@router.post("/my/providers/{provider_id}/sync", summary="同步/更新模型列表")
async def sync_my_provider(
    provider_id: int,
    user_id: str = Depends(deps.get_identity),
    db: AsyncSession = Depends(get_db)
):
    """
    从模板同步最新的模型列表。
    - 补齐缺失的模型
    - 更新已有模型的 context_length 和 type
    - 不会删除用户手动添加的模型
    """
    # 1. 查找供应商及其模板
    provider = await _get_owned_provider(db, user_id, provider_id)
    if not provider.template:
        raise HTTPException(status_code=404, detail="Provider with template not found")
    
    template = provider.template
    if not template.supported_models:
        return {"status": "no_updates", "message": "该模板没有预置模型列表"}
    
    # 2. 对比并同步
    existing_models = {m.model_name: m for m in provider.models}
    added_count = 0
    updated_count = 0
    
    for m_data in template.supported_models:
        m_name = m_data.get("name") if isinstance(m_data, dict) else str(m_data)
        m_type = m_data.get("type", "llm") if isinstance(m_data, dict) else "llm"
        m_ctx = m_data.get("ctx", 4096) if isinstance(m_data, dict) else 4096
        
        if m_name in existing_models:
            # 更新已有模型属性 (context_length, type)
            m_obj = existing_models[m_name]
            if m_obj.context_length != m_ctx or m_obj.model_type != m_type:
                m_obj.context_length = m_ctx
                m_obj.model_type = m_type
                updated_count += 1
        else:
            # 创建新模型
            new_m = ProviderModel(
                provider_id=provider_id,
                model_name=m_name,
                model_type=m_type,
                context_length=m_ctx
            )
            db.add(new_m)
            added_count += 1
            
    await db.commit()
    return {
        "status": "synced",
        "added": added_count,
        "updated": updated_count,
        "total_now": len(existing_models) + added_count
    }


# ============================================================================
# 模型管理（供应商下的模型 CRUD）
# ============================================================================

@router.post("/my/providers/{provider_id}/models", summary="添加模型")
async def add_model(
    provider_id: int,
    model: ModelCreate,
    user_id: str = Depends(deps.get_identity),
    db: AsyncSession = Depends(get_db)
):
    """在供应商下添加一个模型配置"""
    await _get_owned_provider(db, user_id, provider_id)
    
    new_model = ProviderModel(
        provider_id=provider_id,
        model_name=model.model_name,
        model_type=model.model_type,
        context_length=model.context_length,
        max_output_tokens=model.max_output_tokens,
        is_default=model.is_default
    )
    db.add(new_model)
    try:
        await db.commit()
        await db.refresh(new_model)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"模型 '{model.model_name}' 已存在")
    
    return {
        "id": new_model.id, "model_name": new_model.model_name,
        "model_type": new_model.model_type, "context_length": new_model.context_length
    }


@router.get("/my/providers/{provider_id}/models", summary="列出模型")
async def list_models(
    provider_id: int,
    user_id: str = Depends(deps.get_identity),
    db: AsyncSession = Depends(get_db)
):
    """列出供应商下的所有模型"""
    await _get_owned_provider(db, user_id, provider_id)
    result = await db.execute(
        select(ProviderModel).where(ProviderModel.provider_id == provider_id)
    )
    models = result.scalars().all()
    return [
        {
            "id": m.id, "model_name": m.model_name, "model_type": m.model_type,
            "context_length": m.context_length, "max_output_tokens": m.max_output_tokens,
            "is_default": m.is_default
        }
        for m in models
    ]


@router.delete("/my/providers/{provider_id}/models/{model_id}", summary="删除模型")
async def delete_model(
    provider_id: int,
    model_id: int,
    user_id: str = Depends(deps.get_identity),
    db: AsyncSession = Depends(get_db)
):
    """删除供应商下的某个模型"""
    await _get_owned_provider(db, user_id, provider_id)
    result = await db.execute(
        select(ProviderModel).where(ProviderModel.id == model_id, ProviderModel.provider_id == provider_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    await db.delete(model)
    await db.commit()
    return {"status": "deleted", "id": model_id}


# ============================================================================
# 默认模型配置
# ============================================================================

@router.put("/my/default-models", summary="设置默认模型")
async def set_default_model(
    config: DefaultModelSet,
    user_id: str = Depends(deps.get_identity),
    db: AsyncSession = Depends(get_db)
):
    if config.model_type not in ALLOWED_DEFAULT_MODEL_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported model_type")

    provider = await _get_owned_provider(db, user_id, config.provider_id)
    model_exists = any(m.model_name == config.model_name for m in (provider.models or []))
    if not model_exists:
        raise HTTPException(status_code=400, detail="该默认模型不属于所选供应商")

    result = await user_provider_manager.set_default_model(
        db, user_id, config.model_type, config.model_name, config.provider_id
    )
    return {"model_type": result.model_type, "model_name": result.default_model_name, "provider_id": result.provider_id}

@router.get("/my/default-models", summary="查看默认模型")
async def get_my_default_models(
    user_id: str = Depends(deps.get_identity),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(UserModelConfig).where(UserModelConfig.user_id == user_id)
    )
    configs = result.scalars().all()
    return [
        {"model_type": c.model_type, "model_name": c.default_model_name, "provider_id": c.provider_id}
        for c in configs
    ]


@router.get("/my/providers/{provider_id}/health", summary="检查供应商连通性")
async def check_provider_health(
    provider_id: int,
    user_id: str = Depends(deps.get_identity),
    db: AsyncSession = Depends(get_db),
):
    """
    对供应商做轻量连通性探测：
    - 验证归属和 API Key 可解密
    - 使用该供应商下一个 llm/chat 模型做最小 completion 请求
    """
    provider = await _get_owned_provider(db, user_id, provider_id)
    models = provider.models or []
    probe_model = next((m for m in models if m.model_type in {"llm", "chat"}), None) or (models[0] if models else None)

    if not probe_model:
        return {
            "provider_id": provider.id,
            "status": "degraded",
            "reason": "该供应商尚未配置模型",
            "latency_ms": None,
        }

    api_key = None
    if provider.api_key_encrypted:
        try:
            api_key = user_provider_manager.decrypt_key(provider.api_key_encrypted)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"API Key 解密失败: {e}")

    start = time.perf_counter()
    try:
        await completion(
            messages=[{"role": "user", "content": "ping"}],
            model=probe_model.model_name,
            user_id=user_id,
            api_key=api_key,
            api_base=provider.effective_api_base,
            custom_llm_provider=(provider.template.provider_type if provider.template else "openai"),
            stream=False,
            max_tokens=1,
            temperature=0,
            timeout=12,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        return {
            "provider_id": provider.id,
            "status": "healthy",
            "model": probe_model.model_name,
            "latency_ms": latency_ms,
        }
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return {
            "provider_id": provider.id,
            "status": "error",
            "model": probe_model.model_name,
            "latency_ms": latency_ms,
            "error": str(e),
        }
