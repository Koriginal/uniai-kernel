from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
import uuid

from app.core.db import get_db
from app.models.graph_template import GraphTemplateModel
from app.agents.graph_registry import graph_registry

router = APIRouter()

# --- Schemas ---

class GraphTemplateCreate(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    topology: dict
    is_system: bool = False

class GraphTemplateResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    topology: dict
    is_system: bool
    is_active: bool
    version: int

    class Config:
        from_attributes = True

# --- Endpoints ---

@router.post("/templates", response_model=GraphTemplateResponse)
async def create_template(
    template: GraphTemplateCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建新的图编排模板"""
    new_template = GraphTemplateModel(**template.model_dump())
    db.add(new_template)
    await db.commit()
    await db.refresh(new_template)
    return new_template

@router.get("/templates", response_model=List[GraphTemplateResponse])
async def list_templates(
    db: AsyncSession = Depends(get_db)
):
    """列出所有图模板"""
    result = await db.execute(select(GraphTemplateModel))
    return result.scalars().all()

@router.get("/templates/{template_id}", response_model=GraphTemplateResponse)
async def get_template(
    template_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取单个模板详情"""
    template = await db.get(GraphTemplateModel, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template

@router.post("/templates/{template_id}/compile")
async def compile_template(
    template_id: str
):
    """手动触发图模板编译(测试拓扑合法性)"""
    try:
        # 清除旧缓存并尝试获取新实例
        graph_registry.invalidate_cache(template_id)
        graph = await graph_registry.get_compiled_graph(template_id)
        return {
            "status": "success",
            "nodes": list(graph.nodes.keys()),
            "message": f"Graph {template_id} compiled successfully."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Compilation failed: {str(e)}")
