from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional
from app.core.db import get_db
from app.services.memory_service import memory_service
from app.models.memory import UserMemory

router = APIRouter()

class MemoryCreate(BaseModel):
    content: str
    category: Optional[str] = "general"
    user_id: str

class MemoryResponse(BaseModel):
    id: str
    user_id: str
    content: str
    category: str
    created_at: str
    
    class Config:
        from_attributes = True

@router.post("/", response_model=MemoryResponse)
async def create_memory(
    memory: MemoryCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    手动添加用户记忆。
    """
    new_memory = await memory_service._create_new_memory(
        db, memory.user_id, memory.content, memory.category
    )
    await db.commit()
    await db.refresh(new_memory)
    
    return MemoryResponse(
        id=str(new_memory.id),
        user_id=new_memory.user_id,
        content=new_memory.content,
        category=new_memory.category,
        created_at=new_memory.created_at.isoformat()
    )

@router.get("/", response_model=List[MemoryResponse])
async def list_memories(
    user_id: str = Query(..., description="用户 ID"),
    category: Optional[str] = Query(None, description="按分类过滤"),
    db: AsyncSession = Depends(get_db)
):
    """
    查询用户记忆列表。
    """
    memories = await memory_service.get_memories_by_category(db, user_id, category)
    
    return [
        MemoryResponse(
            id=str(m.id),
            user_id=m.user_id,
            content=m.content,
            category=m.category,
            created_at=m.created_at.isoformat()
        )
        for m in memories
    ]

@router.get("/search")
async def search_memories(
    user_id: str = Query(..., description="用户 ID"),
    query: str = Query(..., description="搜索查询"),
    top_k: int = Query(5, ge=1, le=20, description="返回结果数量")
):
    """
    向量语义搜索用户记忆。
    """
    results = await memory_service.search_memories(user_id, query, top_k)
    return {"results": results}

@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    删除指定记忆。
    """
    success = await memory_service.delete_memory(db, memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {"status": "deleted", "id": memory_id}

@router.post("/extract")
async def extract_memories_from_conversation(
    user_id: str = Query(...),
    query: str = Query(...),
    answer: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """
    从对话中提取记忆（仅用于测试，实际应用中应在后台自动触发）。
    """
    memories = await memory_service.extract_memories(db, user_id, query, answer)
    
    return {
        "extracted_count": len(memories),
        "memories": [
            {
                "id": str(m.id),
                "content": m.content,
                "category": m.category
            }
            for m in memories
        ]
    }
