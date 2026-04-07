from typing import Dict, Any, Optional
from app.tools.base import BaseTool
import logging

logger = logging.getLogger(__name__)

class UpsertCanvasTool(BaseTool):
    """
    虚拟画布工具：
    用于将 AI 生成的长篇、结构化内容投射到侧边 Artifact 看板。
    """
    def __init__(self):
        super().__init__(
            name="upsert_canvas",
            label="画布操作",
            description="在侧边看板中创建或更新内容。当需要展示长篇文档(>500字)、完整的源代码文件、复杂的方案、设计草案或可交互的 HTML UI 时，必须调用此工具以提供增强阅读体验。简短回复或小型代码段严禁调用。",
            category="system"
        )
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "看板的标题，例如 'xxx 技术方案' 或 'index.html'。"
                },
                "content": {
                    "type": "string",
                    "description": "投射到看板的完整原始内容（支持 Markdown, 代码文本, 或 HTML 代码）。"
                },
                "type": {
                    "type": "string",
                    "description": "内容的渲染类型，可选值：markdown (文档/方案), code (代码文件), html (网页预览/UI组件)。"
                },
                "language": {
                    "type": "string",
                    "description": "如果类型为 code，请指定编程语言（如 python, typescript 等）。"
                }
            },
            "required": ["title", "content", "type"]
        }

    async def execute(self, title: str, content: str, type: str, language: Optional[str] = None, **kwargs) -> str:
        """
        物理执行逻辑：
        对于虚拟工具，后端仅作记录，核心渲染由前端流式解析器完成。
        """
        logger.info(f"[CanvasTool] Upserting to canvas: {title} ({type})")
        return f"已成功将 '{title}' 投射到侧边看板进行增强展示。"

def register(registry):
    """插件注册接口"""
    registry.register_action(UpsertCanvasTool())
