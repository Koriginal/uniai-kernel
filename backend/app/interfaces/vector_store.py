"""
向量存储抽象接口

支持从 pgvector 平滑迁移到 Milvus/Qdrant 等专用向量数据库。
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from uuid import UUID

class VectorStore(ABC):
    """向量存储抽象基类"""
    
    @abstractmethod
    async def upsert(self, id: UUID, embedding: List[float], metadata: Dict[str, Any]) -> None:
        """插入或更新向量"""
        pass
    
    @abstractmethod
    async def search(
        self, 
        embedding: List[float], 
        filter: Dict[str, Any],
        top_k: int = 5,
        threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """向量相似度搜索"""
        pass
    
    @abstractmethod
    async def delete(self, id: UUID) -> None:
        """删除向量"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
