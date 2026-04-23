from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional
from app.core.db import get_db
from app.services.memory_service import memory_service
from app.models.memory import UserMemory
from app.models.user import User
from app.api import deps

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


def _resolve_target_user(current_user: User, requested_user_id: Optional[str]) -> str:
    if current_user.is_admin and requested_user_id:
        return requested_user_id
    return current_user.id

@router.post("/", response_model=MemoryResponse)
async def create_memory(
    memory: MemoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    手动添加用户记忆。
    """
    target_user_id = _resolve_target_user(current_user, memory.user_id)
    new_memory = await memory_service._create_new_memory(
        db, target_user_id, memory.content, memory.category
    )
    await db.commit()
    await db.refresh(new_memory)
    
    return MemoryResponse(
        id=str(new_memory.id),
        user_id=target_user_id,
        content=new_memory.content,
        category=new_memory.category,
        created_at=new_memory.created_at.isoformat()
    )

@router.get("/", response_model=List[MemoryResponse])
async def list_memories(
    user_id: Optional[str] = Query(None, description="用户 ID（管理员可指定）"),
    category: Optional[str] = Query(None, description="按分类过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    查询用户记忆列表。
    """
    target_user_id = _resolve_target_user(current_user, user_id)
    memories = await memory_service.get_memories_by_category(db, target_user_id, category)
    
    return [
        MemoryResponse(
            id=str(m.id),
            user_id=target_user_id,
            content=m.content,
            category=m.category,
            created_at=m.created_at.isoformat()
        )
        for m in memories
    ]

@router.get("/search")
async def search_memories(
    user_id: Optional[str] = Query(None, description="用户 ID（管理员可指定）"),
    query: str = Query(..., description="搜索查询"),
    top_k: int = Query(5, ge=1, le=20, description="返回结果数量"),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    向量语义搜索用户记忆。
    """
    target_user_id = _resolve_target_user(current_user, user_id)
    results = await memory_service.search_memories(target_user_id, query, top_k)
    return {"results": results}

@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    删除指定记忆。
    """
    memory = await db.get(UserMemory, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    if not current_user.is_admin and memory.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to delete this memory")

    success = await memory_service.delete_memory(db, memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {"status": "deleted", "id": memory_id}

@router.post("/extract")
async def extract_memories_from_conversation(
    user_id: Optional[str] = Query(None),
    query: str = Query(...),
    answer: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    从对话中提取记忆（仅用于测试，实际应用中应在后台自动触发）。
    """
    target_user_id = _resolve_target_user(current_user, user_id)
    memories = await memory_service.extract_memories(db, target_user_id, query, answer)
    
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
