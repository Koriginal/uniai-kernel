from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict, Any
from app.core.db import get_db
from app.models.dynamic_tool import DynamicTool
from app.core.plugins import registry
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class DynamicToolCreate(BaseModel):
    name: str
    label: str
    description: str
    tool_type: str # api, mcp, cli
    config: Dict[str, Any]
    parameters_schema: Dict[str, Any] = {"type": "object", "properties": {}}
    category: str = "custom"

class DynamicToolResponse(BaseModel):
    id: str
    name: str
    label: str
    description: str
    tool_type: str
    config: Dict[str, Any]
    parameters_schema: Dict[str, Any]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

@router.get("/", response_model=List[DynamicToolResponse])
async def list_dynamic_tools(db: AsyncSession = Depends(get_db)):
    """获取所有动态注册工具的原始定义列表"""
    result = await db.execute(select(DynamicTool))
    return result.scalars().all()

@router.post("/", response_model=DynamicToolResponse)
async def create_dynamic_tool(
    data: DynamicToolCreate,
    db: AsyncSession = Depends(get_db)
):
    """注册一个新的动态工具 (API/MCP/CLI)"""
    # 检查重名
    existing = await db.execute(select(DynamicTool).where(DynamicTool.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Tool with name '{data.name}' already exists")

    new_tool = DynamicTool(**data.model_dump())
    db.add(new_tool)
    await db.commit()
    await db.refresh(new_tool)
    
    # 立即尝试加载到当前内核注册表 (热更新)
    await registry.load_dynamic_tools(db)
    
    return new_tool

@router.delete("/{tool_id}")
async def delete_dynamic_tool(tool_id: str, db: AsyncSession = Depends(get_db)):
    """删除动态工具"""
    tool = await db.get(DynamicTool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    await db.delete(tool)
    await db.commit()
    return {"status": "success"}

@router.post("/{tool_id}/toggle")
async def toggle_tool(tool_id: str, db: AsyncSession = Depends(get_db)):
    """启用/禁用动态工具"""
    tool = await db.get(DynamicTool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    tool.is_active = not tool.is_active
    await db.commit()
    return {"status": "success", "is_active": tool.is_active}
