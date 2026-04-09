import logging
import asyncpg
from app.core.config import settings

logger = logging.getLogger(__name__)

async def cleanup_stale_connections():
    """
    清理数据库中处于 'idle in transaction' 状态超过 10 秒的僵尸连接。
    这能有效解决由于事务未及时释放而导致的 DDL (CREATE INDEX) 死锁问题。
    """
    if not settings.ENABLE_DATABASE:
        return

    url = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    
    try:
        conn = await asyncpg.connect(url)
        # 获取所有阻塞的慢事务 PID
        # state = 'idle in transaction' 且 query_start 时间较早
        stale_pids = await conn.fetch("""
            SELECT pid, state_change, query 
            FROM pg_stat_activity 
            WHERE state = 'idle in transaction' 
            AND state_change < now() - interval '10 seconds'
            AND pid <> pg_backend_pid();
        """)
        
        if stale_pids:
            logger.warning(f"[DB-Cleanup] Found {len(stale_pids)} stale 'idle in transaction' connections. Terminating...")
            for row in stale_pids:
                pid = row['pid']
                query = row['query'][:50]
                logger.info(f"[DB-Cleanup] Terminating PID {pid} (Query: {query}...)")
                await conn.execute("SELECT pg_terminate_backend($1)", pid)
            logger.info("[DB-Cleanup] ✅ Cleanup completed.")
        else:
            logger.info("[DB-Cleanup] No stale connections found.")
            
        # [NEW] 监控被阻塞的 DDL 操作
        waiters = await conn.fetch("""
            SELECT pid, query, wait_event_type, wait_event 
            FROM pg_stat_activity 
            WHERE wait_event_type = 'Lock' 
            AND state = 'active';
        """)
        if waiters:
            logger.warning(f"[DB-Cleanup] ⚠️ Found {len(waiters)} sessions waiting for locks. This might cause timeouts.")
            for row in waiters:
                logger.info(f"[DB-Cleanup] Blocked PID {row['pid']} is waiting for lock on query: {row['query'][:100]}")

        await conn.close()
    except Exception as e:
        logger.error(f"[DB-Cleanup] ❌ Failed to cleanup database: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(cleanup_stale_connections())
