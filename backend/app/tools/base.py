from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from app.interfaces.action import BaseAction, ActionMetadata

class BaseTool(BaseAction, ABC):
    """
    UniAI 原子工具基类 (适配 BaseAction)
    
    所有的工具都必须继承此类，以确保其作为“行动资产”被注册到内核。
    """
    def __init__(self, name: str, label: str, description: str, category: str = "utility"):
        metadata = ActionMetadata(
            name=name,
            label=label,
            description=description,
            category=category
        )
        super().__init__(metadata)

    @property
    @abstractmethod
    def parameters_schema(self) -> Dict[str, Any]:
        """返回符合 JSON Schema 标准的工具入参格式"""
        pass
        
    def to_openai_format(self) -> Dict[str, Any]:
        """转换为 OpenAI `tools` 标准格式字典"""
        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": self.parameters_schema
            }
        }
    
    def get_openai_format(self) -> Dict[str, Any]:
        """实现 BaseAction 接口"""
        return self.to_openai_format()
