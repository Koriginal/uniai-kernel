from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel



class ActionMetadata(BaseModel):
    """
    行动（Action/Tool）的元数据定义。
    提供统一的能力资产识别规范。
    """
    name: str # 唯一标识符，如 'web_search'
    label: str # 友好名称，如 '互联网搜索'
    description: str # 详细功能描述，供给 LLM 阅读
    category: str = "utility" # 分类，如 'knowledge', 'system', 'erp'
    icon: Optional[str] = None # 图标（前端展示用）
    version: str = "1.0.0"

class BaseAction(ABC):
    """
    万物皆 Action：定义内核中所有可执行能力的基类。
    """
    def __init__(self, metadata: ActionMetadata):
        self.metadata = metadata

    @abstractmethod
    def get_openai_format(self) -> Dict[str, Any]:
        """
        转换为 OpenAI 兼容的 Function 定义格式。
        """
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        执行具体的行动逻辑。
        """
        pass
