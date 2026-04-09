import logging
import asyncio
from typing import Optional
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.core.db_pool import db_pool_manager

logger = logging.getLogger(__name__)

# 单例缓存
_saver_instance: Optional[AsyncPostgresSaver] = None
# 初始化锁，防止并发执行 setup() 导致数据库 DDL 锁定
_init_lock = asyncio.Lock()

async def create_pg_checkpointer() -> AsyncPostgresSaver:
    """
    创建/获取基于 PostgreSQL 的持久化 checkpointer。
    采用单例并加锁确保初始化过程线程/协程安全。
    """
    global _saver_instance
    
    # 快速路径：已初始化直接返回
    if _saver_instance:
        return _saver_instance
        
    async with _init_lock:
        # 双重校验锁
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
                # 给 DDL 操作足够的容忍度，但在 30 秒后强制失败以防挂起
                await asyncio.wait_for(checkpointer.setup(), timeout=30.0)
                logger.info("[Checkpointer] ✅ Setup/migration completed.")
            except asyncio.TimeoutError:
                logger.error("[Checkpointer] ❌ Setup hung and timed out after 30s! Database might be locked by another process.")
                raise
            
            _saver_instance = checkpointer
            logger.info("[Checkpointer] ✅ Singleton AsyncPostgresSaver initialized.")
            return _saver_instance
            
        except Exception as e:
            logger.error(f"[Checkpointer] ❌ Initialization failed: {e}")
            raise
