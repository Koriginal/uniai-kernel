from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from app.core.plugins import registry

router = APIRouter()

@router.get("/actions", tags=["Asset Inventory"])
async def list_registered_actions() -> List[Dict[str, Any]]:
    """列出内核中所有已注册的行动资产 (Actions) 及其元数据。"""
    return registry.get_action_catalog()

@router.get("/actions/{action_name}", tags=["Asset Inventory"])
async def get_action_detail(action_name: str) -> Dict[str, Any]:
    """获取指定工具的完整详情，含参数 Schema。"""
    action = registry.get_action(action_name)
    if not action:
        raise HTTPException(status_code=404, detail=f"Action '{action_name}' not found")
    
    openai_format = action.get_openai_format()
    return {
        "name": action.metadata.name,
        "label": action.metadata.label,
        "description": action.metadata.description,
        "category": action.metadata.category,
        "icon": action.metadata.icon,
        "version": action.metadata.version,
        "parameters_schema": openai_format.get("function", {}).get("parameters", {}),
        "openai_format": openai_format
    }

@router.get("/status", tags=["Asset Inventory"])
async def get_kernel_status() -> Dict[str, Any]:
    """获取内核运行时的详细统计状态。"""
    actions = registry.get_all_actions()
    categories = {}
    for a in actions:
        cat = a.metadata.category
        categories[cat] = categories.get(cat, 0) + 1
    
    return {
        "actions_count": len(actions),
        "actions_by_category": categories,
        "has_memory_store": registry.get_memory_store() is not None,
        "has_knowledge_base": registry.get_knowledge_base() is not None,
        "registered_actions": [a.metadata.name for a in actions],
        "version": "1.0.0"
    }

@router.get("/scaffold", tags=["Developer Guide"])
async def get_tool_scaffold() -> Dict[str, Any]:
    """
    开发者指南：返回创建新工具的代码模板和规范说明。
    前端工具注册表页面可直接展示此信息。
    """
    return {
        "guide": {
            "title": "UniAI 工具开发指南",
            "steps": [
                "1. 在 backend/app/tools/ 下创建 Python 文件",
                "2. 继承 BaseTool 基类",
                "3. 实现 parameters_schema 属性和 execute 方法",
                "4. 重启内核，工具会被自动发现和注册"
            ]
        },
        "template": '''from typing import Dict, Any
from app.tools.base import BaseTool

class MyCustomTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="my_tool",          # 唯一标识符
            label="我的工具",         # 友好名称
            description="工具描述",   # 供 LLM 阅读
            category="utility"       # 分类
        )
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "参数说明"
                }
            },
            "required": ["param1"]
        }

    async def execute(self, param1: str, **kwargs) -> str:
        return f"Result: {param1}"
''',
        "base_class": "app.tools.base.BaseTool",
        "scan_path": "backend/app/tools/",
        "auto_discovery": True,
        "registration_method": "自动发现（内核启动时扫描 app.tools 包）"
    }

