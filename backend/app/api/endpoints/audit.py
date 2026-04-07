from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional, Dict, Any
from app.core.db import get_db
from app.models.audit import ActionLog
from app.services.audit_service import audit_service
from pydantic import BaseModel, field_validator
from datetime import datetime

router = APIRouter()

class ActionLogResponse(BaseModel):
    id: str
    session_id: Optional[str]
    user_id: str
    agent_id: Optional[str]
    action_name: str
    input_params: Optional[Dict[str, Any]]
    output_result: Optional[str]
    status: str
    duration_ms: float
    request_tokens: int
    response_tokens: int
    total_tokens: int
    cost: float
    created_at: datetime

    @field_validator('request_tokens', 'response_tokens', 'total_tokens', 'cost', mode='before')
    @classmethod
    def convert_none_to_zero(cls, v):
        return v or 0

    class Config:
        from_attributes = True

@router.get("/actions", response_model=List[ActionLogResponse])
async def list_action_logs(
    limit: int = Query(50, ge=1, le=100),
    offset: int = 0,
    action_name: Optional[str] = None,
    user_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """获取行动执行审计日志列表"""
    query = select(ActionLog).order_by(desc(ActionLog.created_at))
    if action_name:
        query = query.where(ActionLog.action_name == action_name)
    if user_id:
        query = query.where(ActionLog.user_id == user_id)
        
    result = await db.execute(query.limit(limit).offset(offset))
    return result.scalars().all()

@router.get("/stats")
async def get_stats(days: int = 7, db: AsyncSession = Depends(get_db)):
    """获取使用情况统计分析数据"""
    return await audit_service.get_usage_stats(db, days)

@router.get("/actions/{log_id}", response_model=ActionLogResponse)
async def get_action_log(log_id: str, db: AsyncSession = Depends(get_db)):
    """获取单个行动日志详情"""
    log = await db.get(ActionLog, log_id)
    return log
