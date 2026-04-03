"""
PgVector 向量存储实现
"""
from typing import List, Dict, Any
from uuid import UUID
from sqlalchemy import text
from app.core.db import SessionLocal
from app.interfaces.vector_store import VectorStore
import logging

logger = logging.getLogger(__name__)

class PgVectorStore(VectorStore):
    """PostgreSQL + pgvector 实现"""
    
    async def upsert(self, id: UUID, embedding: List[float], metadata: Dict[str, Any]) -> None:
        async with SessionLocal() as session:
            await session.execute(
                text("""
                    UPDATE user_memories 
                    SET embedding = :embedding::vector
                    WHERE id = :id
                """),
                {"embedding": str(embedding), "id": str(id)}
            )
            await session.commit()
    
    async def search(
        self, 
        embedding: List[float], 
        filter: Dict[str, Any],
        top_k: int = 5,
        threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        user_id = filter.get("user_id")
        
        async with SessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT 
                        id::text,
                        content,
                        category,
                        metadata_extra,
                        1 - (embedding <=> :query_vec::vector) AS similarity
                    FROM user_memories
                    WHERE user_id = :user_id
                    AND embedding IS NOT NULL
                    ORDER BY embedding <=> :query_vec::vector
                    LIMIT :top_k
                """),
                {
                    "query_vec": str(embedding),
                    "user_id": user_id,
                    "top_k": top_k
                }
            )
            rows = result.fetchall()
        
        results = []
        for row in rows:
            if row[4] >= threshold:
                results.append({
                    "memory_id": row[0],
                    "content": row[1],
                    "category": row[2],
                    "metadata": row[3],
                    "similarity": round(row[4], 3)
                })
        return results
    
    async def delete(self, id: UUID) -> None:
        async with SessionLocal() as session:
            await session.execute(
                text("UPDATE user_memories SET embedding = NULL WHERE id = :id"),
                {"id": str(id)}
            )
            await session.commit()
    
    async def health_check(self) -> bool:
        try:
            async with SessionLocal() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"PgVector health check failed: {e}")
            return False
