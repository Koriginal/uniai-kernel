from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.session import ChatSession
from app.models.message import ChatMessage
from app.services.memory_service import memory_service
from app.core.llm import completion
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ContextService:
    """
    上下文管理服务
    
    核心功能：
    1. 构建 LLM 上下文（整合记忆 + 摘要 + 历史）
    2. 会话滚动压缩
    3. 指代消解
    """
    
    def __init__(self):
        self.short_term_window = 10  # 短期对话窗口
        self.compression_threshold = 20  # 触发压缩的消息数阈值
    
    async def build_context_messages(
        self,
        session_id: str,
        user_id: str,
        current_query: str,
        db_session: AsyncSession,
        enable_memory: bool = True,
        enable_session_summary: bool = True
    ) -> List[Dict[str, str]]:
        """
        构建最终的 LLM 消息列表（整合上下文）。
        
        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            current_query: 当前用户查询
            db_session: 数据库会话
            enable_memory: 是否加载用户长期记忆
            enable_session_summary: 是否加载会话摘要
        
        Returns:
            LLM 消息列表
        """
        messages = []
        
        # 1. System Prompt 基础
        system_prompt_parts = ["你是一个有用的 AI 助手。"]
        
        # 2. 加载用户长期记忆（如果启用）
        if enable_memory and user_id:
            try:
                memories = await memory_service.search_memories(
                    user_id, current_query, top_k=5
                )
                if memories:
                    # 按分类组织记忆
                    cat_map = {}
                    for m in memories:
                        cat = m.get("category", "general")
                        cat_map.setdefault(cat, []).append(m.get("content"))
                    
                    memory_lines = []
                    # 优先展示关键约束
                    if "critical_constraint" in cat_map:
                        memory_lines.append(
                            f"关键约束: {'; '.join(cat_map['critical_constraint'])}"
                        )
                    
                    for cat, items in cat_map.items():
                        if cat != "critical_constraint":
                            memory_lines.append(
                                f"[{cat.upper()}]: {'; '.join(items)}"
                            )
                    
                    system_prompt_parts.append(
                        f"\n<user_profile>\n以下是关于用户的长期记忆，请在回答时考虑这些信息：\n{chr(10).join(memory_lines)}\n</user_profile>"
                    )
                    logger.info(f"[Context] Loaded {len(memories)} memories for user {user_id}")
            except Exception as e:
                logger.warning(f"[Context] Failed to load memories: {e}")
        
        # 3. 加载会话摘要（如果启用）
        if enable_session_summary and session_id:
            try:
                result = await db_session.execute(
                    select(ChatSession).where(ChatSession.id == session_id)
                )
                chat_session = result.scalar_one_or_none()
                if chat_session and chat_session.summary:
                    system_prompt_parts.append(
                        f"\n<session_context>\n会话背景摘要: {chat_session.summary}\n</session_context>"
                    )
                    logger.info(f"[Context] Loaded session summary for {session_id}")
            except Exception as e:
                logger.warning(f"[Context] Failed to load session summary: {e}")
        
        # 4. 组装 System Message
        messages.append({
            "role": "system",
            "content": "\n".join(system_prompt_parts)
        })
        
        # 5. 加载短期对话历史
        try:
            result = await db_session.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(self.short_term_window)
            )
            recent_messages = list(result.scalars().all())
            recent_messages.reverse()  # 按时间正序
            
            for msg in recent_messages:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
            
            if recent_messages:
                logger.info(f"[Context] Loaded {len(recent_messages)} recent messages")
        except Exception as e:
            logger.warning(f"[Context] Failed to load message history: {e}")
        
        # 6. 添加当前用户查询
        messages.append({
            "role": "user",
            "content": current_query
        })
        
        return messages
    
    async def compress_session(
        self,
        session_id: str,
        db_session: AsyncSession
    ) -> Optional[str]:
        """
        压缩会话历史为滚动摘要。
        
        Args:
            session_id: 会话 ID
            db_session: 数据库会话
        
        Returns:
            新生成的摘要，如果失败则返回 None
        """
        try:
            # 1. 加载会话和消息
            result = await db_session.execute(
                select(ChatSession).where(ChatSession.id == session_id)
            )
            chat_session = result.scalar_one_or_none()
            if not chat_session:
                return None
            
            # 2. 加载消息历史
            result = await db_session.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at)
            )
            all_messages = list(result.scalars().all())
            
            # 3. 检查是否需要压缩
            if len(all_messages) <= self.compression_threshold:
                return chat_session.summary
            
            # 4. 提取需要压缩的旧消息（保留最近的短期窗口）
            messages_to_compress = all_messages[:-self.short_term_window]
            if not messages_to_compress:
                return chat_session.summary
            
            # 5. 构建对话片段文本
            text_chunk = "\n".join([
                f"{m.role}: {m.content}" 
                for m in messages_to_compress
            ])
            
            current_summary = chat_session.summary or "无"
            
            # 6. 生成新摘要
            prompt = f"""
任务：更新会话摘要。
[旧摘要]: {current_summary}
[新对话片段]:
{text_chunk[:2000]}  # 限制长度避免 Token 超限

请生成一个新的、包含关键信息（项目进度、关键决定）的简洁摘要（<500字）。
"""
            
            response = await completion([{"role": "user", "content": prompt}])
            new_summary = response.choices[0].message.content.strip()
            
            # 7. 更新数据库
            chat_session.summary = new_summary
            chat_session.compression_count += 1
            db_session.add(chat_session)
            await db_session.commit()
            
            logger.info(f"[Context] Compressed session {session_id}, processed {len(messages_to_compress)} messages")
            return new_summary
            
        except Exception as e:
            logger.error(f"[Context] Session compression failed: {e}")
            return None
    
    async def contextualize_query(
        self,
        query: str,
        recent_history: List[Dict[str, str]]
    ) -> str:
        """
        指代消解：将包含指代的查询转换为独立完整的句子。
        
        Args:
            query: 用户查询
            recent_history: 最近的对话历史
        
        Returns:
            消解后的查询，如果失败则返回原查询
        """
        if not recent_history:
            return query
        
        # 只取最近 3 条
        recent = recent_history[-3:]
        hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
        
        prompt = f"""
任务：指代消解。
[对话]:
{hist_str}
[问题]: {query}
请将问题补全为独立完整的句子。如无需补全原样返回。只返回结果。
"""
        
        try:
            response = await completion([{"role": "user", "content": prompt}])
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"[Context] Query contextualization failed: {e}")
            return query

context_service = ContextService()
