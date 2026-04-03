from typing import List, Union, Dict, Any, Optional
from app.core.config import settings
from app.core.llm import embedding
from app.core.db import SessionLocal
from sqlalchemy import text, select
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

class VectorService:
    def __init__(self):
        self.provider = settings.VECTOR_MODEL_PROVIDER
        self.model_name = settings.VECTOR_MODEL_NAME

    async def check_health(self) -> bool:
        """
        通过尝试简单的 embedding 来检查嵌入服务是否就绪。
        """
        if not self.model_name:
             return True # 如果只是等待配置则假设健康 (如果严格模式则返回 False)
        try:
            await self.embed_text("test")
            return True
        except Exception as e:
            logger.error(f"Vector service health check failed: {e}")
            return False

    async def embed_text(self, text: Union[str, List[str]], model: str = None, user_id: str = "default_user") -> List[List[float]]:
        """
        将字符串或字符串列表嵌入为向量（多租户版本）。
        
        Args:
            text: 要嵌入的文本
            model: 模型名称（可选）
            user_id: 用户 ID
        """
        try:
            # 调用多租户 embedding
            from app.core.llm import embedding
            response = await embedding(
                input=text,
                model=model,
                user_id=user_id
            )
            # 标准化输出: 向量列表
            data = response.get('data', [])
            return [item['embedding'] for item in data]
        except Exception as e:
            logger.error(f"Error in vector service: {e}")
            raise

    # ========================================================================
    # pgvector 集成方法
    # ========================================================================

    async def upsert_memory_vector(
        self, 
        memory_id: UUID, 
        content: str, 
        user_id: str
    ) -> None:
        """
        插入或更新用户记忆向量。
        如果 memory_id 已存在，更新其向量；否则插入（但前提是记忆记录已存在）。
        """
        # 1. 生成向量
        vectors = await self.embed_text(content)
        embedding_vec = vectors[0]  # 单个文本返回单个向量
        
        # 2. 更新数据库
        async with SessionLocal() as session:
            # pgvector 使用 text() 来处理向量类型
            await session.execute(
                text("""
                    UPDATE user_memories 
                    SET embedding = CAST(:embedding AS vector)
                    WHERE id = :memory_id
                """),
                {"embedding": str(embedding_vec), "memory_id": str(memory_id)}
            )
            await session.commit()
            logger.info(f"[Vector] Upserted embedding for memory {memory_id}")

    async def search_similar_memories(
        self, 
        user_id: str, 
        query_text: str, 
        top_k: int = 5,
        threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        检索与查询文本相似的用户记忆。
        
        Args:
            user_id: 用户 ID
            query_text: 查询文本
            top_k: 返回前 K 个结果
            threshold: 相似度阈值 (余弦相似度，0-1)
        
        Returns:
            记忆列表，包含: id, content, category, similarity_score
        """
        # 1. 生成查询向量
        vectors = await self.embed_text(query_text)
        query_embedding = vectors[0]
        
        # 2. 向量检索（使用余弦相似度）
        async with SessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT 
                        id::text,
                        content,
                        category,
                        metadata_extra,
                        1 - (embedding <=> CAST(:query_vec AS vector)) AS similarity
                    FROM user_memories
                    WHERE user_id = :user_id
                    AND embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:query_vec AS vector)
                    LIMIT :top_k
                """),
                {
                    "query_vec": str(query_embedding),
                    "user_id": user_id,
                    "top_k": top_k
                }
            )
            rows = result.fetchall()
            
        # 3. 格式化结果并过滤低相似度
        memories = []
        for row in rows:
            similarity = row[4]
            if similarity >= threshold:
                memories.append({
                    "memory_id": row[0],
                    "content": row[1],
                    "category": row[2],
                    "metadata": row[3],
                    "similarity": round(similarity, 3)
                })
        
        logger.info(f"[Vector] Found {len(memories)} similar memories for user {user_id}")
        return memories

    async def delete_memory_vector(self, memory_id: UUID) -> None:
        """
        删除记忆向量（将 embedding 置为 NULL）。
        注意：这不删除记忆记录本身，只删除向量。
        """
        async with SessionLocal() as session:
            await session.execute(
                text("""
                    UPDATE user_memories 
                    SET embedding = NULL
                    WHERE id = :memory_id
                """),
                {"memory_id": str(memory_id)}
            )
            await session.commit()
            logger.info(f"[Vector] Deleted embedding for memory {memory_id}")

vector_service = VectorService()
