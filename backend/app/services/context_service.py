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
    
    def estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """
        粗略估算消息列表的 Token 消耗 (中文 1.5 字符, 英文 4 字符)
        """
        total = 0
        for m in messages:
            content = m.get("content", "") or ""
            # 中文字符数
            zh_chars = len([c for c in content if '\u4e00' <= c <= '\u9fff'])
            # 其他字符数 (字母、空格、标点)
            other_chars = len(content) - zh_chars
            total += int(zh_chars * 0.8) + int(other_chars / 4) + 4  # 每条消息的基础开销
        return total

    async def build_context_messages(
        self,
        session_id: str,
        user_id: str,
        current_query: str,
        db_session: AsyncSession,
        max_tokens: int = 4096,  # 默认模型上下文限制
        enable_memory: bool = True,
        enable_session_summary: bool = True,
        enable_history: bool = True
    ) -> List[Dict[str, str]]:
        """
        根据 Token 预算，动态构建 LLM 消息列表（最大化历史填充）。
        """
        # 0. 计算预算分配
        # 预留 20% 给系统 Prompt 和记忆，20% 给模型输出，剩余 60% 给历史加载
        history_budget = int(max_tokens * 0.6)
        
        messages = []
        
        # 1. System Prompt 基础
        system_prompt_parts = ["你是一个有用的 AI 助手。"]
        
        # 2. 加载用户长期记忆 (占 10-15% 预算)
        if enable_memory and user_id:
            try:
                memories = await memory_service.search_memories(
                    user_id, current_query, top_k=8
                )
                if memories:
                    memory_lines = [f"- {m.get('content')}" for m in memories]
                    system_prompt_parts.append(
                        f"\n[长期记忆/约束]:\n{chr(10).join(memory_lines)}"
                    )
            except Exception as e:
                logger.warning(f"[Context] Failed to load memories: {e}")
        
        # 3. 加载会话摘要
        if enable_session_summary and session_id:
            try:
                result = await db_session.execute(
                    select(ChatSession).where(ChatSession.id == session_id)
                )
                chat_session = result.scalar_one_or_none()
                if chat_session and chat_session.summary:
                    system_prompt_parts.append(
                        f"\n[前文摘要]: {chat_session.summary}"
                    )
            except Exception as e:
                logger.warning(f"[Context] Failed to load session summary: {e}")
        
        # 4. 组装 System Message
        messages.append({
            "role": "system",
            "content": "\n".join(system_prompt_parts)
        })
        
        # 5. [核心优化] 动态历史装载 (不再限于 10 条)
        if enable_history:
            try:
                # 获取该会话的所有最近消息（按时间倒序）
                result = await db_session.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.created_at.desc())
                    .limit(100) # 先拿 100 条备选
                )
                all_recent = list(result.scalars().all())
                
                history_to_add = []
                current_history_tokens = 0
                
                for msg in all_recent:
                    # 估算该条消息的 Token
                    msg_token = self.estimate_tokens([{"role": msg.role, "content": msg.content}])
                    if current_history_tokens + msg_token > history_budget:
                        break # 预算耗尽
                    
                    history_to_add.insert(0, {
                        "role": msg.role,
                        "content": msg.content
                    })
                    current_history_tokens += msg_token
                
                messages.extend(history_to_add)
                logger.info(f"[Context] Dynamically loaded {len(history_to_add)} messages (estimated {current_history_tokens} tokens)")
            except Exception as e:
                logger.warning(f"[Context] Failed to load history: {e}")
            
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
