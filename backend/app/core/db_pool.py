import logging
from typing import Optional
from psycopg_pool import AsyncConnectionPool
from app.core.config import settings

logger = logging.getLogger(__name__)

class AsyncPoolManager:
    """
    异步数据库连接池管理器 (psycopg 3)
    采用单例模式，确保系统内低层级持久化操作共享池资源。
    主要用于 LangGraph Checkpointer。
    """
    _instance: Optional['AsyncPoolManager'] = None
    _pool: Optional[AsyncConnectionPool] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AsyncPoolManager, cls).__new__(cls)
        return cls._instance

    def _get_conn_info(self) -> str:
        """转换 SQLAlchemy URL 为 psycopg 兼容格式"""
        url = settings.DATABASE_URL
        if not url:
            return f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        
        if "+asyncpg" in url:
            return url.replace("+asyncpg", "")
        return url

    async def init_pool(self):
        """显式初始化并开启连接池 (适配 psycopg_pool 3.2+ 要求)"""
        if self._pool is not None:
            return

        conn_info = self._get_conn_info()
        logger.info("[PoolManager] Initializing global async connection pool...")
        
        # 显式设置 open=False，防止在构造函数中自动开启 (规避警告)
        # 设置 min_size=0，防止启动时因无法满足预留连接数而死锁
        self._pool = AsyncConnectionPool(
            conninfo=conn_info,
            min_size=0,
            max_size=settings.DATABASE_POOL_SIZE if hasattr(settings, 'DATABASE_POOL_SIZE') else 20,
            kwargs={"autocommit": True},
            open=False
        )
        
        await self._pool.open()
        # [FIX] 移除阻塞的 .wait() 调用。连接将在首次执行时建立。
        logger.info(f"[PoolManager] ✅ Global async connection pool initialized (min_size=0, max_size={self._pool.max_size}).")

    async def close_pool(self):
        """优雅关闭连接池并释放资源"""
        if self._pool:
            logger.info("[PoolManager] Closing global async connection pool...")
            await self._pool.close()
            self._pool = None
            logger.info("[PoolManager] 🛑 Pool closed.")

    @property
    def pool(self) -> AsyncConnectionPool:
        if self._pool is None:
            raise RuntimeError("[PoolManager] Pool is not initialized. Call init_pool() during lifespan startup.")
        return self._pool

# 全局单例实例
db_pool_manager = AsyncPoolManager()
