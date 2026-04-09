import logging
from typing import Optional
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.core.db_pool import db_pool_manager

logger = logging.getLogger(__name__)

# 单例缓存，防止重复初始化迁移表
_saver_instance: Optional[AsyncPostgresSaver] = None

async def create_pg_checkpointer() -> AsyncPostgresSaver:
    """
    创建/获取基于 PostgreSQL 的持久化 checkpointer。
    该实现依赖于 app/core/db_pool 提供的单例连接池。
    """
    global _saver_instance
    if _saver_instance:
        return _saver_instance
        
    try:
        # 1. 从核心池管理器获取单例池
        pool = db_pool_manager.pool
        
        # 2. 初始化 LangGraph Postgres Saver (共享池)
        checkpointer = AsyncPostgresSaver(pool)
        
        # 3. 异步初始化表结构 (迁移脚本)
        logger.info("[Checkpointer] Running setup/migration for Postgres checkpointer...")
        try:
            import asyncio
            await asyncio.wait_for(checkpointer.setup(), timeout=30.0)
            logger.info("[Checkpointer] ✅ Setup/migration completed.")
        except asyncio.TimeoutError:
            logger.error("[Checkpointer] ❌ Setup hung and timed out after 30s! Database might be locked.")
            raise
        
        _saver_instance = checkpointer
        logger.info("[Checkpointer] ✅ Singleton AsyncPostgresSaver initialized.")
        return _saver_instance
        
    except Exception as e:
        logger.error(f"[Checkpointer] ❌ Initialization failed: {e}")
        # 如果获取连接池失败，通常意味着系统启动流程有问题
        raise
