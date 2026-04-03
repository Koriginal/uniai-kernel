from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class IKnowledgeBase(ABC):
    """
    企业私有知识库引擎接口
    """

    @abstractmethod
    async def add_document(self, tenant_id: str, content: str, document_id: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """向知识空间内摄入文档切片"""
        pass

    @abstractmethod
    async def search_documents(self, tenant_id: str, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """从私有知识库中检索参考片段"""
        pass
