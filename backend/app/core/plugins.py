import logging
from typing import Dict, Any, Type, Optional, List
from app.interfaces.memory_store import IMemoryStore
from app.interfaces.knowledge_base import IKnowledgeBase
from app.interfaces.action import BaseAction, ActionMetadata
import os
import importlib
import pkgutil

logger = logging.getLogger(__name__)

class PluginRegistry:
    """
    UniAI 内核资产注册表 (Kernel Asset Registry)
    
    统一管理内存、知识库以及所有外部可执行的 Action (行动资产)。
    """
    def __init__(self):
        # 核心系统服务插件
        self._memory_store: Optional[IMemoryStore] = None
        self._knowledge_base: Optional[IKnowledgeBase] = None
        
        # 挂载的行动资产 (AIP Actions / Tools)
        self._actions: Dict[str, BaseAction] = {}
        self._dynamic_action_names: set[str] = set()
        self._dynamic_action_diagnostics: Dict[str, Dict[str, Any]] = {}

    def register_memory_store(self, store: IMemoryStore):
        self._memory_store = store
        logger.info(f"[Registry] MemoryStore registered: {store.__class__.__name__}")

    def get_memory_store(self) -> Optional[IMemoryStore]:
        return self._memory_store

    def register_knowledge_base(self, kb: IKnowledgeBase):
        self._knowledge_base = kb
        logger.info(f"[Registry] KnowledgeBase registered: {kb.__class__.__name__}")

    def get_knowledge_base(self) -> Optional[IKnowledgeBase]:
        return self._knowledge_base

    def register_action(self, action: BaseAction):
        """注册一个标准化的行动资产"""
        name = action.metadata.name
        self._actions[name] = action
        logger.info(f"[Registry] Action registered: {name} ({action.metadata.label})")

    def get_action(self, name: str) -> Optional[BaseAction]:
        return self._actions.get(name)

    def unregister_action(self, name: str):
        """从运行时注册表移除指定工具。"""
        if name in self._actions:
            self._actions.pop(name, None)
            logger.info(f"[Registry] Action unregistered: {name}")

    def clear_dynamic_actions(self):
        """清空当前运行时中由数据库动态加载的工具。"""
        for name in list(self._dynamic_action_names):
            self.unregister_action(name)
        self._dynamic_action_names.clear()
        self._dynamic_action_diagnostics.clear()

    def get_dynamic_action_diagnostics(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._dynamic_action_diagnostics)

    async def execute_action(self, name: str, **kwargs):
        action = self.get_action(name)
        if not action:
            raise ValueError(f"Tool '{name}' not found in registry.")
        return await action.execute(**kwargs)

    def get_all_actions(self) -> List[BaseAction]:
        """获取所有已注册的行动资产"""
        return list(self._actions.values())

    def get_all_tools(self) -> List[BaseAction]:
        """[向下兼容] 返回所有行动资产"""
        return self.get_all_actions()

    def get_action_catalog(self) -> List[Dict[str, Any]]:
        """获取资产目录清单 (用于管理后台或前端展示)"""
        return [
            {
                "name": a.metadata.name,
                "label": a.metadata.label,
                "description": a.metadata.description,
                "category": a.metadata.category,
                "icon": a.metadata.icon,
                "version": a.metadata.version
            }
            for a in self._actions.values()
        ]

    def load_plugins(self, package_name: str = "app.tools"):
        """
        [框架化演进] 自动化扫描并加载指定包下的插件。
        """
        try:
            package = importlib.import_module(package_name)
            package_path = package.__path__
            
            for _, name, is_pkg in pkgutil.iter_modules(package_path):
                full_module_name = f"{package_name}.{name}"
                module = importlib.import_module(full_module_name)
                
                # 方案 A: 寻找模块内定义的 BaseAction 子类并自动实例化
                # 方案 B: 寻找模块内的 register(registry) 函数 (推荐，更灵活)
                if hasattr(module, "register"):
                    module.register(self)
                else:
                    # 备选：寻找所有继承自 BaseAction 的类（非抽象类）
                    import inspect
                    for _, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, BaseAction) and obj != BaseAction and not inspect.isabstract(obj):
                            try:
                                self.register_action(obj())
                            except Exception as e:
                                logger.error(f"[Registry] Failed to auto-register class {obj.__name__}: {e}")
            
            logger.info(f"[Registry] ✅ Auto-loaded plugins from {package_name}")
        except Exception as e:
            logger.error(f"[Registry] ❌ Failed to load plugins from {package_name}: {e}")

    async def load_dynamic_tools(self, db_session):
        """
        从数据库加载动态注册的工具 (API/MCP/CLI)。
        """
        from app.models.dynamic_tool import DynamicTool
        from app.services.ext_tools import ApiTool, McpTool, CliTool
        from sqlalchemy import select

        try:
            self.clear_dynamic_actions()
            result = await db_session.execute(select(DynamicTool).where(DynamicTool.is_active == True))
            tools = result.scalars().all()
            
            for t in tools:
                try:
                    instance = None
                    if t.tool_type == "api":
                        instance = ApiTool(
                            name=t.name, label=t.label, description=t.description,
                            url=t.config.get("url"), method=t.config.get("method", "POST"),
                            headers=t.config.get("headers"), schema=t.parameters_schema,
                            timeout_seconds=float(t.config.get("timeout_seconds", 20.0))
                        )
                    elif t.tool_type == "mcp":
                        transport = t.config.get("transport", "stdio")
                        if transport == "sse":
                            from app.services.ext_tools import McpSseTool
                            instance = McpSseTool(
                                name=t.name, label=t.label, description=t.description,
                                url=t.config.get("url"),
                                schema=t.parameters_schema,
                                timeout_seconds=float(t.config.get("timeout_seconds", 30.0))
                            )
                        else:
                            instance = McpTool(
                                name=t.name, label=t.label, description=t.description,
                                command=t.config.get("command"), args=t.config.get("args"),
                                schema=t.parameters_schema,
                                timeout_seconds=float(t.config.get("timeout_seconds", 30.0))
                            )
                    elif t.tool_type == "cli":
                        instance = CliTool(
                            name=t.name, label=t.label, description=t.description,
                            script=t.config.get("script"), schema=t.parameters_schema,
                            timeout_seconds=float(t.config.get("timeout_seconds", 30.0))
                        )
                    
                    if instance:
                        self.register_action(instance)
                        self._dynamic_action_names.add(instance.metadata.name)
                        self._dynamic_action_diagnostics[t.name] = {
                            "status": "loaded",
                            "tool_type": t.tool_type,
                            "tool_id": t.id,
                            "error": None,
                        }
                except Exception as e:
                    logger.error(f"[Registry] Failed to load dynamic tool {t.name}: {e}")
                    self._dynamic_action_diagnostics[t.name] = {
                        "status": "error",
                        "tool_type": t.tool_type,
                        "tool_id": t.id,
                        "error": str(e),
                    }
            
            logger.info(f"[Registry] ✅ Loaded {len(tools)} dynamic tools from DB")
        except Exception as e:
            logger.error(f"[Registry] ❌ Failed to query dynamic tools: {e}")

# 全局单例
registry = PluginRegistry()
