import time
import logging
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from app.core.db import SessionLocal
from app.models.graph_execution import GraphExecution

logger = logging.getLogger(__name__)

class GraphTelemetry:
    """
    图推理遥测控制器
    采用 AOP 面向切面模式设计，通过异步上下文管理器记录每个节点的执行详情。
    """
    
    @asynccontextmanager
    async def trace_node(
        self, 
        node_name: str, 
        state: Dict[str, Any], 
        config: Dict[str, Any]
    ):
        """
        节点执行追踪器 (Async Context Manager)
        用法:
            async with telemetry.trace_node("agent", state, config):
                # 节点执行内容
        """
        c = config.get("configurable", {})
        session_id = c.get("session_id")
        request_id = c.get("request_id")
        agent_id = state.get("current_agent_id")
        
        start_time = time.perf_counter()
        status = "success"
        error_msg = None
        
        # 记录初始快照 (可选)
        logger.debug(f"[Telemetry] Entering node: {node_name} (Session: {session_id})")
        
        try:
            yield
        except Exception as e:
            status = "error"
            error_msg = str(e)
            logger.error(f"[Telemetry] Node {node_name} failed: {e}")
            raise
        finally:
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000
            
            # 提取指标 (从状态中推敲)
            # 注意：这些字段需要由节点处理逻辑更新到 state 或从 state 提取
            input_tokens = state.get("last_input_tokens", 0)
            output_tokens = state.get("last_output_tokens", 0)
            tool_calls = state.get("pending_tool_calls", [])
            tool_calls_count = len(tool_calls) if isinstance(tool_calls, list) else 0
            
            # 异步保存到数据库 (非阻塞)
            # 注意：在生产环境建议使用任务队列或批量写入，此处先实现直接写入以满足本期要求
            asyncio.create_task(self._persist_execution(
                session_id=session_id,
                request_id=request_id,
                node_name=node_name,
                agent_id=agent_id,
                status=status,
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                tool_calls_count=tool_calls_count,
                error_message=error_msg
            ))

    async def _persist_execution(self, **kwargs):
        """持久化到数据库"""
        try:
            async with SessionLocal() as db:
                execution = GraphExecution(**kwargs)
                db.add(execution)
                await db.commit()
        except Exception as e:
            # 遥测本身的故障不应干扰主业务
            logger.warning(f"[Telemetry] Persistence failed: {e}")

# 全局单例
telemetry = GraphTelemetry()
