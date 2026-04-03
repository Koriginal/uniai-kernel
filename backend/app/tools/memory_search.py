from typing import Dict, Any
from app.tools.base import BaseTool
import logging

logger = logging.getLogger(__name__)

class MemorySearchTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="search_user_memory",
            label="用户记忆检索",
            description="搜索用户长期记忆库，获取用户的偏好、历史约束或重要的过往事实。",
            category="knowledge"
        )
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "用户的唯一标识 ID。"
                },
                "query": {
                    "type": "string",
                    "description": "检索关键词，例如 '用户职业' 或 '代码风格偏好'。"
                }
            },
            "required": ["user_id", "query"]
        }

    async def execute(self, user_id: str, query: str, **kwargs) -> str:
        try:
            # 延迟引入避免循环依赖
            from app.services.memory_service import memory_service
            
            memories = await memory_service.search_memories(user_id=user_id, query=query, top_k=3)
            if not memories:
                return "记忆库中未找到相关信息。"
            
            result = []
            for i, mem in enumerate(memories):
                result.append(f"{i+1}. {mem.get('content', '')}")
            return "\\n".join(result)
            
        except Exception as e:
            logger.error(f"[MemorySearchTool] Error: {e}")
            return "内部错误：记忆检索失败。"
