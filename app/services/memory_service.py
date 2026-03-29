from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.memory import UserMemory
from app.services.vector_service import vector_service
from app.core.llm import completion
from app.utils.helpers import clean_json
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class MemoryService:
    """
    用户记忆管理服务
    
    核心功能：
    1. 从对话中提取记忆（CoT 提取）
    2. 记忆去重与巩固（仲裁机制）
    3. 向量检索相似记忆
    4. CRUD 操作
    """
    
    async def extract_memories(
        self, 
        session: AsyncSession,
        user_id: str, 
        query: str, 
        answer: str
    ) -> List[UserMemory]:
        """
        从对话中提取长期记忆（CoT 提取）。
        
        Args:
            session: 数据库会话
            user_id: 用户 ID
            query: 用户问题
            answer: AI 回答
        
        Returns:
            提取并保存的记忆对象列表
        """
        if not user_id or user_id == "default_user":
            return []

        prompt = f"""
作为用户的"认知记忆管家"，请分析下面的对话，提取关于用户的**长期事实**或**重要偏好**。

[对话内容]
User: {query}
AI: {answer}

[提取标准]
1. **长期价值**: 仅提取在这个会话结束后依然有价值的信息。
   - ✅ 有效: "我是左撇子", "我正在备考CPA", "请永远用Python回复代码", "我女儿叫小红".
   - ❌ 无效: "把这个改成红色", "今天好热", "帮我写个邮件", "谢谢".
2. **去语境化**: 提取的事实必须是独立的。
   - ❌ "他喜欢这个"
   - ✅ "用户喜欢科幻电影"
3. **分类**:
   - `basic_info`: 姓名、年龄、职业、地点.
   - `preference`: 风格偏好、忌讳、格式要求.
   - `critical_constraint`: 绝对的指令约束 (如: "不准使用表情包").
   - `history`: 关键的人生经历或过往事件.
   - `work`: 工作相关的项目、技能.

[输出格式 - JSON List]
请严格按照以下格式输出，包含 `reasoning` (思考过程) 和 `fact` (事实对象)。
[
  {{
    "reasoning": "用户提到在备考CPA，这是一个持续的状态，值得记录。",
    "fact": {{ "content": "用户正在备考CPA证书", "category": "work" }}
  }}
]
如果不包含值得记忆的信息，返回空列表 []。

请返回 JSON：
"""
        
        try:
            response = await completion([{"role": "user", "content": prompt}])
            response_text = response.choices[0].message.content
            
            # 清洗 JSON
            data = json.loads(clean_json(response_text))
            
            if not isinstance(data, list):
                return []

            # 提取并巩固记忆
            saved_memories = []
            for item in data:
                fact = item.get("fact")
                if fact:
                    content = fact.get("content")
                    category = fact.get("category", "general")
                    if content:
                        memory = await self.consolidate_memory(
                            session, user_id, content, category
                        )
                        if memory:
                            saved_memories.append(memory)
            
            if saved_memories:
                await session.commit()
                logger.info(f"[Memory] Extracted {len(saved_memories)} memories for user {user_id}")
            
            return saved_memories
            
        except Exception as e:
            logger.error(f"[Memory] Extraction failed: {e}")
            return []

    async def consolidate_memory(
        self, 
        session: AsyncSession,
        user_id: str, 
        new_content: str, 
        category: str
    ) -> Optional[UserMemory]:
        """
        记忆巩固：决定新信息是 Insert, Update 还是 Ignore。
        
        Args:
            session: 数据库会话
            user_id: 用户 ID
            new_content: 新记忆内容
            category: 记忆分类
        
        Returns:
            创建或更新的记忆对象，如果被忽略则返回 None
        """
        # 1. 检索相似记忆（阈值 0.8）
        similar_memories = await vector_service.search_similar_memories(
            user_id, new_content, top_k=1, threshold=0.8
        )
        
        if not similar_memories:
            # 无相似记忆，直接创建
            return await self._create_new_memory(session, user_id, new_content, category)

        # 2. 存在相似记忆 -> 仲裁
        existing_mem = similar_memories[0]
        existing_content = existing_mem["content"]
        existing_id = existing_mem["memory_id"]
        
        arbitration_prompt = f"""
[记忆库维护]
请判断新信息与旧记忆的关系。

[旧记忆]: "{existing_content}"
[新信息]: "{new_content}"

操作指令:
1. **IGNORE**: 新信息完全被旧记忆包含，或者不如旧记忆详细。
2. **REPLACE**: 新信息与旧记忆**冲突**（如时间更新、状态变更），或者新信息更准确。
3. **MERGE**: 两者互补，合并成一条更完整的信息。
4. **ADD**: 两者描述不同维度的信息，应该共存。

返回 JSON: {{ "action": "IGNORE" | "REPLACE" | "MERGE" | "ADD", "new_text": "..." }}
"""
        
        try:
            res = await completion([{"role": "user", "content": arbitration_prompt}])
            decision_text = res.choices[0].message.content
            decision = json.loads(clean_json(decision_text))
            
            action = decision.get("action")
            text = decision.get("new_text")
            
            if action == "IGNORE":
                logger.info(f"[Memory] IGNORE: {new_content}")
                return None
            elif action in ["REPLACE", "MERGE"] and text:
                # 更新现有记忆
                result = await session.execute(
                    select(UserMemory).where(UserMemory.id == existing_id)
                )
                mem_item = result.scalar_one_or_none()
                if mem_item:
                    mem_item.content = text
                    mem_item.updated_at = datetime.utcnow()
                    session.add(mem_item)
                    await session.flush()
                    
                    # 更新向量
                    await vector_service.upsert_memory_vector(mem_item.id, text, user_id)
                    logger.info(f"[Memory] {action}: {text}")
                    return mem_item
            elif action == "ADD":
                return await self._create_new_memory(session, user_id, new_content, category)
                
        except Exception as e:
            logger.error(f"[Memory] Arbitration failed: {e}")
            # Fallback: 出错时新增
            return await self._create_new_memory(session, user_id, new_content, category)

    async def _create_new_memory(
        self, 
        session: AsyncSession,
        user_id: str, 
        content: str, 
        category: str
    ) -> UserMemory:
        """创建新记忆并生成向量"""
        item = UserMemory(user_id=user_id, content=content, category=category)
        session.add(item)
        await session.flush()
        
        # 生成并保存向量
        await vector_service.upsert_memory_vector(item.id, content, user_id)
        
        logger.info(f"[Memory] Created: {content}")
        return item

    async def search_memories(
        self, 
        user_id: str, 
        query_text: str, 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """向量检索用户记忆"""
        return await vector_service.search_similar_memories(user_id, query_text, top_k)

    async def get_memories_by_category(
        self, 
        session: AsyncSession,
        user_id: str, 
        category: Optional[str] = None
    ) -> List[UserMemory]:
        """按分类查询记忆"""
        query = select(UserMemory).where(UserMemory.user_id == user_id)
        if category:
            query = query.where(UserMemory.category == category)
        result = await session.execute(query.order_by(UserMemory.created_at.desc()))
        return list(result.scalars().all())

    async def delete_memory(
        self, 
        session: AsyncSession,
        memory_id: str
    ) -> bool:
        """删除记忆（包括向量）"""
        try:
            result = await session.execute(
                select(UserMemory).where(UserMemory.id == memory_id)
            )
            memory = result.scalar_one_or_none()
            if not memory:
                return False
            
            await session.delete(memory)
            await session.commit()
            
            # 向量会通过数据库级联删除或在这里显式删除
            # 由于我们的设计是向量在同一行，所以会自动删除
            
            logger.info(f"[Memory] Deleted memory {memory_id}")
            return True
        except Exception as e:
            logger.error(f"[Memory] Delete failed: {e}")
            return False

memory_service = MemoryService()
