from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Union, Dict, Any
from app.core.db import get_db
from app.models.agent import AgentProfile
from app.models.openai import ChatCompletionRequest, ChatCompletionMessage
from app.services.agent_service import agent_service
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uuid
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Schemas ---

class AgentProfileCreate(BaseModel):
    name: str
    description: Optional[str] = None
    model_config_id: int
    system_prompt: Optional[str] = None
    tools: List[str] = []
    is_public: bool = False

class AgentProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    model_config_id: Optional[int] = None
    system_prompt: Optional[str] = None
    tools: Optional[List[str]] = None
    is_public: Optional[bool] = None

class AgentProfileResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    model_config_id: int
    system_prompt: Optional[str] = None
    tools: List[str]
    is_public: bool
    is_active: bool

    class Config:
        from_attributes = True

class AgentChatRequest(BaseModel):
    query: Union[str, List[Dict[str, Any]]] # 支持图片/多模态
    session_id: Optional[str] = None
    stream: bool = True
    enable_memory: bool = False
    enable_swarm: bool = True
    enable_canvas: bool = True
    skip_save_user: bool = False # 控制是否重复保存用户消息

# --- Endpoints ---

@router.post("/", response_model=AgentProfileResponse)
async def create_agent_profile(
    profile: AgentProfileCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建新的智能体 Profile"""
    new_profile = AgentProfile(
        id=f"agent-{uuid.uuid4().hex[:8]}",
        name=profile.name,
        description=profile.description,
        model_config_id=profile.model_config_id,
        system_prompt=profile.system_prompt,
        tools=profile.tools,
        is_public=profile.is_public,
        user_id="local_dev" # 暂时硬编码，后续由鉴权中间件提供
    )
    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)
    return new_profile

@router.get("/", response_model=List[AgentProfileResponse])
async def list_agent_profiles(
    db: AsyncSession = Depends(get_db)
):
    """列出所有智能体 Profile"""
    result = await db.execute(select(AgentProfile))
    return result.scalars().all()

@router.get("/{agent_id}", response_model=AgentProfileResponse)
async def get_agent_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取单个智能体详情"""
    profile = await db.get(AgentProfile, agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    return profile

@router.put("/{agent_id}", response_model=AgentProfileResponse)
async def update_agent_profile(
    agent_id: str,
    update: AgentProfileUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新智能体配置"""
    profile = await db.get(AgentProfile, agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    
    try:
        for field, value in update.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)
        
        await db.commit()
        await db.refresh(profile)
        return profile
    except Exception as e:
        logger.error(f"Error updating agent {agent_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

@router.delete("/{agent_id}")
async def delete_agent_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db)
):
    """删除智能体"""
    profile = await db.get(AgentProfile, agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    
    await db.delete(profile)
    await db.commit()
    return {"status": "deleted"}

@router.post("/{agent_id}/chat")
async def agent_chat(
    agent_id: str,
    request_data: AgentChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    智能体业务对话专线：
    采用极简 Schema，自动封装为 OpenAI 协议并由 AgentService 执行。
    """
    profile = await db.get(AgentProfile, agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent profile not found")
        
    # 从中中间件提取身份
    user_id = getattr(request.state, "user_id", "admin")

    # 模拟构造一个标准 OpenAI 请求体
    openai_request = ChatCompletionRequest(
        model=agent_id,
        messages=[
            ChatCompletionMessage(role="user", content=request_data.query)
        ],
        stream=request_data.stream,
        skip_save_user=request_data.skip_save_user
    )
    
    if request_data.stream:
        return StreamingResponse(
            agent_service.chat_stream(
                request=openai_request,
                user_id=user_id,
                session_id=request_data.session_id,
                enable_memory=request_data.enable_memory,
                enable_swarm=request_data.enable_swarm,
                enable_canvas=request_data.enable_canvas
            ),
            media_type="text/event-stream"
        )
    else:
        # 统一使用业务层方法接入
        return await agent_service.chat(
            request=openai_request,
            user_id=user_id,
            session_id=request_data.session_id,
            enable_memory=request_data.enable_memory,
            enable_swarm=request_data.enable_swarm,
            enable_canvas=request_data.enable_canvas
        )
