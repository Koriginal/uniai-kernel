import asyncio
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List, Dict, Any, Optional
from uuid import UUID

from app.core.db import SessionLocal
from app.models.memory import UserMemory
from app.core.llm import completion
from app.core.config import settings
from app.services.vector_service import vector_service

logger = logging.getLogger(__name__)

class MemoryService:
    """
    认知记忆服务：负责用户长期记忆的提取、索引、检索与维护。
    整合了基于 LLM 的事实提纯与基于 pgvector 的语义检索。
    """

    # --- 核心检索接口 ---
    
    async def search_memories(
        self, 
        user_id: str, 
        query: str, 
        top_k: int = 5,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        检索与当前查询相关的长期记忆（语义检索）。
        """
        if not settings.ENABLE_MEMORY:
            return []
            
        try:
            # 1. 向量语义检索
            results = await vector_service.search_similar_memories(
                user_id=user_id,
                query_text=query,
                top_k=top_k * 2, # 取更多候选进行重排
                threshold=threshold
            )
            
            if not results:
                return []

            # 2. 结合 Importance 进行重排 (Rerank)
            # 公式：综合得分 = 相似度 * (1 + 权重系数 * 重要性/5)
            scored_results = []
            async with SessionLocal() as db:
                for r in results:
                    try:
                        m_id = r.get("memory_id")
                        m_obj = await db.get(UserMemory, UUID(m_id))
                        if m_obj:
                            # 简单的加权公式
                            boost = 1 + (m_obj.importance / 5.0) * 0.2 # 最高提升 20%
                            r["score"] = r["similarity"] * boost
                            scored_results.append(r)
                    except Exception as e:
                        logger.warning(f"[Memory] Failed to process memory {r.get('memory_id')}: {e}")
                        continue
            
            # 按最终得分排序并截断
            scored_results.sort(key=lambda x: x["score"], reverse=True)
            return scored_results[:top_k]

        except Exception as e:
            if "No valid Embedding model" in str(e):
                logger.info(f"[Memory] Semantic search skipped (No model config), using basic matching.")
            else:
                logger.warning(f"[Memory] Semantic search failed, falling back to basic matching: {e}")
            # 降级：基础文本匹配
            async with SessionLocal() as db:
                stmt = select(UserMemory).where(
                    UserMemory.user_id == user_id
                ).order_by(UserMemory.created_at.desc()).limit(top_k)
                result = await db.execute(stmt)
                rows = result.scalars().all()
                return [{"content": r.content, "category": r.category} for r in rows]

    # --- 记忆生命周期管理 ---

    async def add_memory(
        self, 
        user_id: str, 
        content: str, 
        category: str = "general", 
        importance: int = 1,
        source_session_id: str = None,
        metadata: dict = None
    ) -> UserMemory:
        """
        手动添加一条记忆，并同步更新向量。
        """
        async with SessionLocal() as db:
            new_memory = UserMemory(
                user_id=user_id,
                content=content,
                category=category,
                importance=importance,
                source_session_id=source_session_id,
                metadata_extra=metadata or {}
            )
            db.add(new_memory)
            await db.commit()
            await db.refresh(new_memory)
            
            # 异步更新向量
            asyncio.create_task(vector_service.upsert_memory_vector(new_memory.id, content, user_id))
            return new_memory

    async def delete_memory(self, memory_id: UUID) -> bool:
        """
        删除记忆及其向量。
        """
        async with SessionLocal() as db:
            stmt = delete(UserMemory).where(UserMemory.id == memory_id)
            result = await db.execute(stmt)
            await db.commit()
            
            # 清理向量
            asyncio.create_task(vector_service.delete_memory_vector(memory_id))
            return result.rowcount > 0

    # --- [Phase 20] 自动提取与提纯 (优化版提示词) ---

    async def extract_and_persist_facts(self, user_id: str, messages: List[Dict[str, Any]], session_id: str = None):
        """
        异步自适应提纯：从对话中提取新事实并入库（高级 Prompt 优化版）。
        """
        if not settings.MEMORY_EXTRACTION_ENABLED:
            return

        logger.info(f"[Memory] Starting professional fact extraction for: {user_id}")
        
        # 优化后的高级 Prompt
        extraction_prompt = (
            "## Role: 认知心理学专家 & 资深知识工程师\n"
            "## Task: 用户的长程属性深度萃取\n"
            "## Input: 最近一次的对话历史\n\n"
            "## Extraction Criteria:\n"
            "1. **稳定性**: 仅记录不会随时间轻易改变的特征（如职业、偏好、习惯）。\n"
            "2. **原子化**: 每条记忆必须是独立的陈述句，严禁包含代词（我、他、它）。\n"
            "3. **高信度**: 忽略调侃、玩笑或显而易见的废话。\n"
            "4. **分类与权重**: 评价每条事实的重要性（1-5分）。\n\n"
            "## Output Format (Strict JSON Array):\n"
            '  [{"content": "事实陈述", "category": "分类", "importance": 权重数字}]\n'
            "  *Categories*: basic_info, preference, constraint, work, history.\n\n"
            "## 对话历史:\n"
        )
        
        history_text = "\n".join([f"{m.get('role')}: {m.get('content')}" for m in messages[-10:] if m.get("content")])
        
        try:
            response = await completion(
                model=settings.DEFAULT_LLM_MODEL or "qwen-flash", 
                messages=[
                    {"role": "system", "content": "You are a professional Cognitive Profiler. Reply ONLY in raw JSON array JSON."},
                    {"role": "user", "content": extraction_prompt + history_text}
                ],
                user_id=user_id,
                stream=False
            )
            
            if not response or not response.choices:
                return
                
            raw_text = response.choices[0].message.content.strip()
            if "```" in raw_text:
                raw_text = raw_text.split("```")[1].replace("json", "").strip()
                
            facts = json.loads(raw_text)
            
            for fact in facts:
                content = fact.get("content")
                category = fact.get("category", "general")
                importance = fact.get("importance", 1)
                
                if not content: continue
                
                # 语义去重 (针对新内容进行高相似度拦截)
                existing = await self.search_memories(user_id, content, top_k=1, threshold=0.88)
                if existing:
                    logger.debug(f"[Memory] Fact skipped (high similarity): {content}")
                    continue
                
                # 保存新记忆 (携带权重与溯源)
                await self.add_memory(
                    user_id=user_id,
                    content=content,
                    category=category,
                    importance=importance,
                    source_session_id=session_id,
                    metadata={"extractor": "cognitive-profiler-v2"}
                )
                
        except Exception as e:
            logger.error(f"[Memory] High-precision extraction failed: {e}")

memory_service = MemoryService()
