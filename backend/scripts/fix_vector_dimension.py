import asyncio
import os
import sys
import logging

# 确保能导入 app 内容
sys.path.append(os.path.join(os.getcwd(), "backend"))
sys.path.append(os.getcwd())

from app.core.db import engine
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_dimension():
    logger.info("Starting dimension correction (1536 -> 1024)...")
    
    async with engine.begin() as conn:
        # 1. 删除依赖旧维度的索引
        logger.info("Dropping old index...")
        await conn.execute(text("DROP INDEX IF EXISTS user_memories_embedding_hnsw_idx;"))
        
        # 2. 修改字段维度
        logger.info("Altering column type to vector(1024)...")
        try:
            await conn.execute(text("ALTER TABLE user_memories ALTER COLUMN embedding TYPE vector(1024);"))
            logger.info("Column type updated.")
        except Exception as e:
            logger.error(f"Failed to alter column type: {e}")
            # 如果 alter 失败，尝试删除重加
            logger.info("Attempting to recreation column...")
            await conn.execute(text("ALTER TABLE user_memories DROP COLUMN IF EXISTS embedding;"))
            await conn.execute(text("ALTER TABLE user_memories ADD COLUMN embedding vector(1024);"))

        # 3. 重建索引
        logger.info("Recreating HNSW index for 1024 dimensions...")
        await conn.execute(text("CREATE INDEX IF NOT EXISTS user_memories_embedding_hnsw_idx ON user_memories USING hnsw (embedding vector_cosine_ops);"))
        
    logger.info("Dimension correction completed successfully.")

if __name__ == "__main__":
    asyncio.run(fix_dimension())
