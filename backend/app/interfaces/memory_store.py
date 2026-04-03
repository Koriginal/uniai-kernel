from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class IMemoryStore(ABC):
    """
    智能体记忆存储总线接口
    """
    
    @abstractmethod
    async def add_memory(self, user_id: str, content: str, category: str = "general", metadata: Optional[Dict[str, Any]] = None) -> bool:
        """存储一条新的记忆"""
        pass

    @abstractmethod
    async def search_memories(self, user_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """语义化检索记忆"""
        pass
        
    @abstractmethod
    async def save_session_context(self, session_id: str, user_id: str, messages: List[Dict[str, Any]], summary: Optional[str] = None) -> bool:
        """保存当前会话窗口上下文"""
        pass
        
    @abstractmethod
    async def get_session_context(self, session_id: str, user_id: str) -> Dict[str, Any]:
        """获取当前会话摘要与历史"""
        pass
