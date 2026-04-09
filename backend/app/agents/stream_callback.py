"""
UniAI Kernel — 流式回调桥接器

提供节点内部到外部 SSE 生成器的异步消息桥梁。
图节点通过 StreamCallback 推送 SSE 事件，AgentService 从中读取并 yield 给前端。
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


class StreamCallback:
    """
    节点 → SSE 的异步桥接器。

    用法：
        # 在 AgentService 中创建
        callback = StreamCallback()

        # 在图节点中推送
        await callback.emit('data: {"type": "status", ...}\\n\\n')

        # 在 AgentService 中消费
        async for event in callback.iter_events():
            yield event
    """

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._closed = False

    async def emit(self, data: str):
        """推送一条 SSE 格式的数据行"""
        if self._closed:
            logger.warning("[StreamCallback] Attempted to emit after close")
            return
        await self._queue.put(data)

    async def emit_node_event(self, event_type: str, node_name: str, payload: dict = None):
        """
        推送图节点执行进度事件给前端。
        event_type: "start" | "end"
        """
        import json
        event_data = {
            "type": "node_event",
            "event": event_type,
            "node": node_name,
            "payload": payload or {}
        }
        sse_data = f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
        await self.emit(sse_data)

    async def close(self):
        """标记流结束"""
        self._closed = True
        await self._queue.put(None)  # 哨兵值

    async def iter_events(self):
        """
        异步迭代器：持续读取队列中的事件，直到收到关闭信号。
        用于 AgentService.chat_stream 中 yield SSE 数据。
        """
        while True:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=30.0)
                if event is None:
                    break
                yield event
            except asyncio.TimeoutError:
                # 超时保活：发送空格避免连接断开
                yield " "
